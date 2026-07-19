# -*- coding: utf-8 -*-
"""Inicialización específica de Windows que debe correr ANTES de importar tkinter."""


def apply_startup_init():
    # DPI awareness ANTES de crear cualquier ventana de tkinter. Sin esto, en
    # pantallas con escalado (125%/150%) o multi-monitor, Windows re-escala la
    # ventana después de que Tkinter calculó su posición y el overlay aparece
    # movido de donde el código pidió (ver CLAUDE.md).
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
