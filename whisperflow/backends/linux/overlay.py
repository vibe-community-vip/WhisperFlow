# -*- coding: utf-8 -*-
"""Overlay flotante en Linux: tkinter + ``-alpha``.

Linux no tiene ``-transparentcolor`` (eso es Windows) ni el problema de ClearType,
así que ``-alpha`` es seguro. Igual que en Mac: esquinas cuadradas, porque sin
colorkey no hay forma de transparentar el área fuera de la cápsula. Divergencia
visual aceptada.
"""
from whisperflow.core import overlay_base as ob


class LinuxOverlayBackend(ob.TkOverlayBase):
    def _configure_window(self, root, tk):
        try:
            root.attributes("-alpha", 0.96)
        except Exception:
            pass
        try:
            # Sugerirle al WM que es un overlay: sin decoración, sin barra de tareas.
            root.attributes("-type", "splash")
        except Exception:
            pass
