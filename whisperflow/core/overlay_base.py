# -*- coding: utf-8 -*-
"""Indicador flotante (núcleo): interfaz + animación compartida sobre Tk.

El **dibujo** vive en ``overlay_render.py`` (Pillow: degradados, halos, tipografía
fina). Acá está lo que lo mueve: la cola de comandos, el suavizado de las barras
contra el nivel del micrófono y el blit de la imagen al canvas.

Antes, cada ``backends/<os>/overlay.py`` repetía la misma animación con primitivas
de ``tkinter.Canvas`` (tres copias que había que mantener sincronizadas). Ahora el
backend de cada SO solo aporta lo que de verdad cambia entre sistemas: cómo se crea
y se hace transparente la ventana (``_configure_window``).

  - Windows: ``-transparentcolor`` (colorkey, esquinas redondeadas) + ``-alpha``
    (opacidad) + ``WS_EX_NOACTIVATE``/``WS_EX_TRANSPARENT``. Windows aplica colorkey
    y alpha a la vez; el texto lo rasteriza Pillow, así que no hay ClearType que romper.
  - Mac/Linux: ``-alpha`` (ahí no hay colorkey).
"""
import math
import queue as _queue
import threading
from abc import ABC, abstractmethod

from whisperflow.core import config
from whisperflow.core import overlay_render as render
from whisperflow.core import recorder

# Geometría/paleta: fuente única de verdad en overlay_render (re-exportadas por
# comodidad para los backends, que necesitan el tamaño de la ventana).
PILL_W = render.PILL_W
PILL_H = render.PILL_H
KEY_COLOR_HEX = "#%02x%02x%02x" % render.KEY_COLOR

FRAME_MS = 33            # ~30 fps: el blit de una imagen de 236x34 cuesta ~0.04 ms
BOTTOM_MARGIN = 110      # distancia desde el borde inferior de la pantalla (modo "bottom")
CURSOR_GAP = 22          # px entre la punta del puntero y el borde inferior de la cápsula
CURSOR_BELOW = 30        # si no cabe encima (puntero pegado arriba), va debajo: salta el puntero
EDGE_MARGIN = 8          # nunca pegada al borde del monitor

# --- Aviso de "sin señal" ---------------------------------------------------
# Si mientras grabás el micrófono no entrega nada, el indicador lo dice en vez de
# fingir que todo va bien. Nace de un caso real: el micrófono del portátil dejó de
# captar, la app grababa y transcribía sin errores... silencio, y el usuario solo
# veía "grabando" con las barras quietas. Whisper encima alucinaba texto repetido
# sobre ese silencio, así que el fallo se veía como "transcribe cualquier cosa".
#
# SPEECH_FLOOR está en la escala de ``recorder.current_mic_level`` (rms*9 acotado a
# 1.0). El umbral del VAD es 0.008 de RMS, que en esa escala son ~0.072; se usa algo
# por debajo para no acusar en falso a quien habla bajito.
SPEECH_FLOOR = 0.045
SILENT_SECONDS = 2.0     # hay que estar así de tiempo callado antes de avisar
_SILENT_FRAMES = int(SILENT_SECONDS * 1000 / FRAME_MS)

# --- Pausas al hablar --------------------------------------------------------
# El aviso de arriba solo tiene sentido si el micrófono NUNCA entregó voz en este
# dictado. Si ya se oyó voz y después hay silencio, es una pausa (p. ej. leyendo
# algo en voz alta): en vez de "sin señal", la cápsula se desvanece hasta
# OVERLAY_PAUSE_OPACITY para no tapar lo que se lee, con el punto aún respirando
# para que se note que sigue grabando. Al volver a hablar recupera la opacidad.
PAUSE_SECONDS = 1.2
_PAUSE_FRAMES = int(PAUSE_SECONDS * 1000 / FRAME_MS)
FADE_OUT_STEP = 0.04     # por frame: desvanecerse tarda ~0.4 s, sin sobresalto
FADE_IN_STEP = 0.25      # volver al hablar es casi inmediato


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

    def _work_area(self, root, x, y):
        """(izq, arriba, der, abajo) del área útil del monitor que contiene (x, y).
        Default: la pantalla principal entera; Windows lo afina por monitor."""
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()

    def _place(self, root):
        """Posición de la cápsula al aparecer. Se calcula una vez por dictado: si
        siguiera al puntero mientras grabás, se movería bajo la vista y distrae."""
        if config.OVERLAY_POSITION == "bottom":
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"+{(sw - PILL_W) // 2}+{sh - BOTTOM_MARGIN}")
            return
        px, py = root.winfo_pointerxy()
        left, top, right, bottom = self._work_area(root, px, py)
        x = px - PILL_W // 2
        y = py - CURSOR_GAP - PILL_H
        if y < top + EDGE_MARGIN:                 # no cabe encima: debajo del puntero
            y = py + CURSOR_BELOW
        x = max(left + EDGE_MARGIN, min(x, right - EDGE_MARGIN - PILL_W))
        y = max(top + EDGE_MARGIN, min(y, bottom - EDGE_MARGIN - PILL_H))
        root.geometry(f"+{x}+{y}")

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

        state = {"name": "loading", "visible": False, "tick": 0, "silent": 0,
                 "heard": False, "alpha": config.OVERLAY_OPACITY}
        levels = [0.0] * render.BAR_COUNT

        def set_alpha(value):
            if abs(value - state["alpha"]) < 0.005:
                return
            state["alpha"] = value
            try:
                root.attributes("-alpha", value)
            except Exception:
                pass

        def poll():
            try:
                while True:
                    cmd, payload = self._queue.get_nowait()
                    if cmd == "show":
                        state["name"] = payload
                        if not state["visible"]:
                            try:
                                self._place(root)
                            except Exception as e:   # posicionar nunca debe impedir mostrarla
                                print(f"[whisperflow] overlay sin reposicionar ({e})", flush=True)
                            set_alpha(config.OVERLAY_OPACITY)
                            root.deiconify()
                            state["visible"] = True
                    elif cmd == "hide" and state["visible"]:
                        root.withdraw()
                        state["visible"] = False
                        state["silent"] = 0
                        state["heard"] = False
                        for i in range(render.BAR_COUNT):
                            levels[i] = 0.0
            except _queue.Empty:
                pass

            if state["visible"]:
                state["tick"] += 1
                tick = state["tick"]
                name = state["name"]
                grabando = name in ("recording", "hands_free")
                alpha_goal = config.OVERLAY_OPACITY
                if grabando:
                    target = recorder.current_mic_level
                    # Contar cuánto lleva el micrófono sin entregar nada.
                    if target < SPEECH_FLOOR:
                        state["silent"] += 1
                    else:
                        state["silent"] = 0
                        state["heard"] = True
                    if state["heard"]:
                        if state["silent"] >= _PAUSE_FRAMES:
                            alpha_goal = min(alpha_goal, config.OVERLAY_PAUSE_OPACITY)
                    elif state["silent"] >= _SILENT_FRAMES:
                        name = "no_signal"      # solo lo que se DIBUJA; el estado real no cambia
                elif name == "processing":
                    target = 0.35 + 0.25 * math.sin(tick * 0.20)   # pulso, no hay mic en vivo
                else:
                    target = 0.0

                if alpha_goal < state["alpha"]:
                    set_alpha(max(alpha_goal, state["alpha"] - FADE_OUT_STEP))
                elif alpha_goal > state["alpha"]:
                    set_alpha(min(alpha_goal, state["alpha"] + FADE_IN_STEP))

                for i in range(render.BAR_COUNT):
                    wobble = 0.72 + 0.28 * math.sin(tick * 0.30 + i * 0.9)  # da vida a cada barra
                    goal = min(1.0, target * wobble)
                    # Ataque rápido y caída lenta, como un medidor de audio de verdad:
                    # con un suavizado simétrico los picos de voz se perdían y las
                    # barras apenas se movían, que es justo lo que no dejaba ver si el
                    # micrófono estaba captando.
                    factor = 0.65 if goal > levels[i] else 0.18
                    levels[i] += (goal - levels[i]) * factor
                dot_step = int(1.5 + 1.5 * math.sin(tick * 0.13))           # el punto respira
                photo.paste(self._renderer.frame(name, levels, dot_step))
            root.after(FRAME_MS, poll)

        root.after(FRAME_MS, poll)
        self._root = root
