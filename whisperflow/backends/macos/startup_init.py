# -*- coding: utf-8 -*-
"""Inicialización de macOS (no-op: Tk maneja Retina/DPI por sí solo)."""


def apply_startup_init():
    # En Mac no hace falta SetProcessDpiAwareness (eso es de Windows). Tk es
    # consciente del DPI de Retina nativamente.
    pass
