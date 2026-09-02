# -*- coding: utf-8 -*-
"""Hotkeys globales en macOS vía CGEventTap nativo (pyobjc/Quartz) — default en Mac.

- **Suprime teclas**: devolviendo ``None`` se traga el evento => una tecla registrada
  ``,``/``.``/``-`` no se escriben mientras se graba (igual que Windows).
- **No pasa por ``HIServices.AXIsProcessTrusted``** (pynput crashea ahí con algunos
  combos pyobjc). Usa Quartz directo.
- **Aordes configurables** vía ``.env``: el acorde de re-pegar se detecta por flags.

Requiere **Accesibilidad** y **Supervisión de entrada**. Si el tap activo (con supresión)
no se crea por permisos, cae a un tap solo-escucha (PTT/manos-libres funcionan, pero las
no hay supresión) y avisa claro por consola.
"""
import threading

from whisperflow.core.hotkey_base import HotkeyBackend, HotkeyCapabilities

# Keycodes (layout US) -> nombre CANÓNICO (la máquina de estados habla en canónicos:
# super=Cmd, ctrl, alt, shift, space, o el carácter).
_KC = {
    0x37: "super", 0x36: "super",        # left/right command
    0x3B: "ctrl", 0x3E: "ctrl",          # left/right control
    0x3A: "alt", 0x3D: "alt",            # left/right option
    0x38: "shift", 0x3C: "shift",
    0x31: "space",
    0x2B: ",", 0x2F: ".", 0x1B: "-",     # teclas registrables por register_suppressible_key
    0x06: "z",
}
_MODS = {"super", "ctrl", "alt", "shift"}


class _Event:
    __slots__ = ("name", "event_type")

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


class CGEventTapHotkeyBackend(HotkeyBackend):
    def __init__(self):
        self._on_event = None
        self._suppressible = {}
        self._repaste_cb = None
        self._repaste_mods = []
        self._repaste_terminal = []
        self._repaste_flag = {}
        self._tap = None
        self._source = None
        self._thread = None
        self._runloop = None

    @staticmethod
    def _accessibility_trusted():
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            return None

    def start(self, on_event):
        self._on_event = on_event
        import Quartz
        from CoreFoundation import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
                                    CFRunLoopGetCurrent, CFRunLoopRun, kCFRunLoopCommonModes)

        _FLAG = {"super": Quartz.kCGEventFlagMaskCommand,
                 "ctrl": Quartz.kCGEventFlagMaskControl,
                 "alt": Quartz.kCGEventFlagMaskAlternate,
                 "shift": Quartz.kCGEventFlagMaskShift}
        _FLAGS_CHANGED = Quartz.kCGEventFlagsChanged
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))

        def tap_callback(proxy, event_type, event, refcon):
            try:
                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                name = _KC.get(keycode, "")

                # down/up: para modificadores (FlagsChanged) se deduce de los flags.
                if event_type == _FLAGS_CHANGED and name in _MODS:
                    is_down = bool(Quartz.CGEventGetFlags(event) & _FLAG[name])
                    etype = "down" if is_down else "up"
                else:
                    is_down = event_type == Quartz.kCGEventKeyDown
                    etype = "down" if is_down else "up"

                # Re-paste (acorde configurable): tecla terminal + todos sus modificadores.
                if is_down and name in self._repaste_terminal:
                    flags = Quartz.CGEventGetFlags(event)
                    if all(flags & self._repaste_flag[m] for m in self._repaste_mods):
                        if self._repaste_cb is not None:
                            try:
                                self._repaste_cb()
                            except Exception:
                                pass
                        return None  # tragamos la tecla terminal

                # Despachar y SUPRIMIR si el handler devuelve False.
                if name in self._suppressible:
                    try:
                        swallow = self._suppressible[name](_Event(name, etype))
                    except Exception:
                        swallow = True
                    return None if not swallow else event

                # Modificadores / espacio -> máquina de estados.
                if name in _MODS or name == "space":
                    try:
                        on_event(_Event(name, etype))
                    except Exception:
                        pass
                return event
            except Exception:
                return event

        # 1) tap activo (con supresión). Requiere Accesibilidad + Supervisión de entrada.
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, 0, Quartz.kCGEventTapOptionDefault, mask, tap_callback, None)

        if self._tap is None:
            acc = self._accessibility_trusted()
            print("[whisperflow] CGEventTap activo (con supresión) NO se pudo crear.", flush=True)
            print(f"  Accesibilidad (AXIsProcessTrusted): "
                  f"{'OK' if acc else ('FALTA' if acc is False else 'desconocido')}", flush=True)
            print("  Configuración del Sistema > Privacidad y seguridad:", flush=True)
            print("    - Accesibilidad           -> activá tu terminal (Warp) Y Python", flush=True)
            print("    - Supervisión de entrada  -> ídem (necesaria para el tap activo)", flush=True)
            print("  Si ya estaban, quitá (-) y volvé a agregar; luego RELANZÁ la app.", flush=True)
            # 2) fallback: tap solo-escucha (puede funcionar con menos permisos; sin suprimir).
            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap, 0, Quartz.kCGEventTapOptionListenOnly,
                mask, tap_callback, None)
            if self._tap is not None:
                print("[whisperflow] Usando tap en modo solo-escucha: PTT/manos-libres OK, "
                      "pero no habrá supresión de teclas.", flush=True)
            else:
                print("[whisperflow] Tampoco se pudo crear el tap. Atajos desactivados.", flush=True)
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

    def register_hotkey(self, keys, callback):
        # keys canónicos. Separo modificadores (vistos por flags) de la tecla terminal.
        import Quartz
        flag = {"super": Quartz.kCGEventFlagMaskCommand, "ctrl": Quartz.kCGEventFlagMaskControl,
                "alt": Quartz.kCGEventFlagMaskAlternate, "shift": Quartz.kCGEventFlagMaskShift}
        self._repaste_cb = callback
        self._repaste_mods = [k for k in keys if k in flag]
        self._repaste_terminal = [k for k in keys if k not in flag]
        self._repaste_flag = flag

    def send(self, combo):
        _send_combo(combo)

    def release(self, key):
        pass

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
    """Síntesis mínima vía CGEvent (el pegado real lo hace paste.py)."""
    try:
        import Quartz
        mods_map = {"cmd": (0x37, Quartz.kCGEventFlagMaskCommand),
                    "super": (0x37, Quartz.kCGEventFlagMaskCommand),
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
