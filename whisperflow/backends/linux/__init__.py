# -*- coding: utf-8 -*-
"""Backend de Linux (X11 con soporte; Wayland best-effort).

AVISO (Fase 6): no verificado en Linux real durante el desarrollo. py_compile OK;
REQUIERE verificación runtime. X11 funciona con setup (grupo ``input`` / regla udev
para ``/dev/uinput``, y ``xclip``+``xdotool`` instalados). Wayland es best-effort: la
captura global de hotkeys y la inyección de teclas están restringidas por el portal de
seguridad; ver nota en hotkey.py.
"""
