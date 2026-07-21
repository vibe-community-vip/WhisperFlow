# -*- coding: utf-8 -*-
"""Indicador flotante (núcleo): colores, geometría y matemática compartida.

La creación concreta de la ventana es específica de cada OS:
  - Windows: ``-transparentcolor`` + ``WS_EX_NOACTIVATE`` (esquinas redondeadas,
    sin robar foco). NUNCA ``-alpha``: rompe el ClearType de Windows (flecos).
  - Mac/Linux: ``-alpha`` (el problema de ClearType NO aplica ahí).
Esos detalles viven en ``backends/<os>/overlay.py``.
"""
from abc import ABC, abstractmethod
from typing import Optional

OVERLAY_STATE_COLOR = {
    "recording":  "#8ecae6",  # celeste suave (antes rojo, muy invasivo)
    "hands_free": "#b3a4e8",  # lavanda suave
    "processing": "#e8c98d",  # ámbar suave
    "loading":    "#9aa0a6",  # gris: modelo cargando (Fase 2)
}
OVERLAY_TEXT_COLOR = "#d8d8dd"  # texto neutro; solo punto/borde/barritas llevan color de estado
OVERLAY_STATE_TEXT = {
    "recording":  "Grabando",
    "hands_free": "Manos libres",
    "processing": "Procesando",
    "loading":    "Cargando modelo",
}
OVERLAY_PROFILE_TEXT = {
    "friendly": "amigable",
    "professional": "profesional",
}

# Geometría de la píldora y de las barritas del ecualizador (a la derecha del texto).
PILL_W, PILL_H, PILL_RADIUS = 240, 36, 15
DOT_RADIUS = 3.5
BAR_COUNT = 4
BAR_W, BAR_GAP = 3, 3
BAR_MIN_H, BAR_MAX_H = 3, 15
BARS_AREA_W = BAR_COUNT * BAR_W + (BAR_COUNT - 1) * BAR_GAP
PAD_LEFT, PAD_RIGHT = 14, 12


def rounded_rect_points(x1, y1, x2, y2, r):
    # 12 puntos de control que, con smooth=True, Tkinter interpola como una curva
    # continua: el resultado se ve como un rectángulo con esquinas redondeadas.
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class OverlayBackend(ABC):
    """Indicador flotante. Corre en su propio hilo con su propio Tk; los comandos
    llegan por cola desde los hilos de teclado (nunca tocar widgets desde otro hilo)."""

    @abstractmethod
    def start(self) -> None: ...
    @abstractmethod
    def show(self, state: str, profile: Optional[str] = None) -> None: ...
    @abstractmethod
    def hide(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...

    def run_mainloop(self) -> None:
        """Solo backends donde el loop de UI debe correr en el hilo principal
        (macOS: Tk exige el hilo principal y arrancar ANTES que pystray). Default: no-op."""
        pass
