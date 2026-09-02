# -*- coding: utf-8 -*-
"""Indicador flotante (núcleo): interfaz + animación compartida sobre Tk.

El **dibujo** vive en ``overlay_render.py`` (Pillow: degradados, halos, tipografía
fina). Acá está lo que lo mueve: la cola de comandos, el suavizado de las barras
contra el nivel del micrófono y el blit de la imagen al canvas.

Antes, cada ``backends/<os>/overlay.py`` repetía la misma animación con primitivas
de ``tkinter.Canvas`` (tres copias que había que mantener sincronizadas). Ahora el
backend de cada SO solo aporta lo que de verdad cambia entre sistemas: cómo se crea
y se hace transparente la ventana (``_configure_window``).

  - Windows: ``-transparentcolor`` (colorkey) + ``WS_EX_NOACTIVATE``. NUNCA
    ``-alpha``: rompe el ClearType de Windows. Como el texto ahora lo rasteriza
    Pillow y no Tk, el colorkey es la única razón que queda para evitar ``-alpha``.
  - Mac/Linux: ``-alpha`` (ahí no hay colorkey ni ClearType).
"""
import math
import queue as _queue
import threading
from abc import ABC, abstractmethod

from whisperflow.core import overlay_render as render
from whisperflow.core import recorder

# Geometría/paleta: fuente única de verdad en overlay_render (re-exportadas por
# comodidad para los backends, que necesitan el tamaño de la ventana).
PILL_W = render.PILL_W
PILL_H = render.PILL_H
KEY_COLOR_HEX = "#%02x%02x%02x" % render.KEY_COLOR

FRAME_MS = 33            # ~30 fps: el blit de una imagen de 236x34 cuesta ~0.04 ms
BOTTOM_MARGIN = 110      # distancia desde el borde inferior de la pantalla


class OverlayBackend(ABC):
    """Indicador flotante. Corre con su propio Tk; los comandos llegan por cola
    desde los hilos de teclado (nunca tocar widgets desde otro hilo)."""

    @abstractmethod
    def start(self) -> None: ...
    @abstractmethod
    def show(self, state: str) -> None: ...
    @abstractmethod
    def hide(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...

    def run_mainloop(self) -> None:
        """Solo backends donde el loop de UI debe correr en el hilo principal
        (macOS: Tk exige el hilo principal y arrancar ANTES que pystray). Default: no-op."""
        pass


class TkOverlayBase(OverlayBackend):
    """Implementación común sobre Tk. Cada SO solo implementa ``_configure_window``."""

    def __init__(self):
        self._queue = _queue.Queue()
        self._root = None
        self._thread = None
        self._renderer = None

    # --- lo único que cambia por SO ---
    @abstractmethod
    def _configure_window(self, root, tk) -> None:
        """Aplica la transparencia y los flags de ventana propios del SO.
        Se llama con la ventana ya dimensionada y posicionada, antes de mostrarla."""

    # --- API pública ---
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, state):
        self._queue.put(("show", state))

    def hide(self):
        self._queue.put(("hide", None))

    def stop(self):
        # El hilo es daemon con su propio mainloop; el os._exit(0) del orquestador
        # termina todo el proceso. No hay forma limpia de cortar mainloop desde aquí.
        pass

    # --- ciclo de vida ---
    def _run(self):
        self._build()
        self._root.mainloop()

    def _build(self):
        import tkinter as tk
        from PIL import ImageTk

        self._renderer = render.OverlayRenderer()
        self._renderer.prewarm()   # rasteriza fondos y sprites antes del primer show

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{PILL_W}x{PILL_H}+{(sw - PILL_W) // 2}+{sh - BOTTOM_MARGIN}")
        root.config(bg=KEY_COLOR_HEX)

        canvas = tk.Canvas(root, width=PILL_W, height=PILL_H, bg=KEY_COLOR_HEX,
                           highlightthickness=0, borderwidth=0)
        canvas.pack(fill="both", expand=True)

        self._configure_window(root, tk)

        # master=root explícito: ImageTk usa el root "por defecto" de tkinter si no se
        # le dice cuál, y ese puede ser otro (o vivir en otro hilo) -> "main thread is
        # not in main loop".
        photo = ImageTk.PhotoImage(self._renderer.frame("loading", [0.0] * render.BAR_COUNT),
                                   master=root)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas._wf_photo = photo   # referencia viva: sin esto el GC borra la imagen

        root.update_idletasks()
        root.withdraw()

        state = {"name": "loading", "visible": False, "tick": 0}
        levels = [0.0] * render.BAR_COUNT

        def poll():
            try:
                while True:
                    cmd, payload = self._queue.get_nowait()
                    if cmd == "show":
                        state["name"] = payload
                        if not state["visible"]:
                            root.deiconify()
                            state["visible"] = True
                    elif cmd == "hide" and state["visible"]:
                        root.withdraw()
                        state["visible"] = False
                        for i in range(render.BAR_COUNT):
                            levels[i] = 0.0
            except _queue.Empty:
                pass

            if state["visible"]:
                state["tick"] += 1
                tick = state["tick"]
                name = state["name"]
                if name in ("recording", "hands_free"):
                    target = recorder.current_mic_level
                elif name == "processing":
                    target = 0.35 + 0.25 * math.sin(tick * 0.20)   # pulso, no hay mic en vivo
                else:
                    target = 0.0
                for i in range(render.BAR_COUNT):
                    wobble = 0.72 + 0.28 * math.sin(tick * 0.30 + i * 0.9)  # da vida a cada barra
                    goal = min(1.0, target * wobble)
                    levels[i] += (goal - levels[i]) * 0.30                  # suaviza
                dot_step = int(1.5 + 1.5 * math.sin(tick * 0.13))           # el punto respira
                photo.paste(self._renderer.frame(name, levels, dot_step))
            root.after(FRAME_MS, poll)

        root.after(FRAME_MS, poll)
        self._root = root
