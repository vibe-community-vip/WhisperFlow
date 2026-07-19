# -*- coding: utf-8 -*-
"""Overlay flotante en macOS: tkinter + ``-alpha`` (sin transparentcolor, que es Windows-only).

Diferencias visuales frente a Windows (aceptadas en el plan):
  - **Esquinas cuadradas**: en Mac no hay ``-transparentcolor`` (colorkey), así que no
    podemos hacer transparente el área fuera de la píldora. El overlay es una pequeña
    barra oscura abajo al centro.
  - **Sí usa ``-alpha``**: el problema de ClearType que en Windows obliga a evitar
    ``-alpha`` NO aplica en Mac, así que la transparencia es segura.

No robar foco: intento best-effort vía pyobjc (NSPanel/level); si pyobjc falla, igual
funciona pero puede activarse al hacer clic. REQUIERE ajuste/verificación en Mac real.
"""
import math
import queue as _queue
import threading

from whisperflow.core import overlay_base as ob
from whisperflow.core import recorder


class MacOSOverlayBackend(ob.OverlayBackend):
    def __init__(self):
        self._queue = _queue.Queue()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, state, profile=None):
        self._queue.put(("show", (state, profile)))

    def hide(self):
        self._queue.put(("hide", None))

    def stop(self):
        pass  # daemon + os._exit(0)

    def _run(self):
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 1.0)   # Mac permite -alpha (sin problema ClearType)
        except Exception:
            pass

        W, H = ob.PILL_W, ob.PILL_H
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - 110}")

        # Barra oscura (sin transparentcolor: el fondo es el color de la píldora).
        bg = "#232328"
        root.config(bg=bg)
        canvas = tk.Canvas(root, width=W, height=H, bg=bg, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        dot_cx = ob.PAD_LEFT + ob.DOT_RADIUS
        dot = canvas.create_oval(dot_cx - ob.DOT_RADIUS, H / 2 - ob.DOT_RADIUS,
                                 dot_cx + ob.DOT_RADIUS, H / 2 + ob.DOT_RADIUS,
                                 fill="#8ecae6", outline="")
        text_x = dot_cx + ob.DOT_RADIUS + 7
        label = canvas.create_text(text_x, H // 2, text="", fill=ob.OVERLAY_TEXT_COLOR, anchor="w",
                                   font=("Helvetica", 10, "bold"))
        bars_x0 = W - ob.PAD_RIGHT - ob.BARS_AREA_W
        bar_items = []
        for i in range(ob.BAR_COUNT):
            cx = bars_x0 + i * (ob.BAR_W + ob.BAR_GAP) + ob.BAR_W / 2
            item = canvas.create_rectangle(cx - ob.BAR_W / 2, H / 2 - ob.BAR_MIN_H / 2,
                                           cx + ob.BAR_W / 2, H / 2 + ob.BAR_MIN_H / 2,
                                           fill="#8ecae6", outline="")
            bar_items.append(item)

        root.update_idletasks()
        # Best-effort: poner la ventana por encima y no activable vía pyobjc.
        try:
            import AppKit
            # El NSWindow del toplevel de Tk: subimos por la cadena de views.
            # (Esto es lo más frágil del backend Mac; si falla, se atrapa y sigue.)
            nswin = AppKit.NSApp.mainWindow()
            # No es fiable obtener el NSWindow exacto de Tk sin más bridging; dejamos
            # que -topmost haga el trabajo. Ajustar en Mac real si roba foco.
        except Exception:
            pass

        root.withdraw()
        visible = False
        current_state = "recording"
        current_color = ob.OVERLAY_STATE_COLOR["recording"]
        bar_heights = [float(ob.BAR_MIN_H)] * ob.BAR_COUNT
        tick = 0

        def redraw_bars():
            nonlocal tick
            tick += 1
            if current_state in ("recording", "hands_free"):
                target_level = recorder.current_mic_level
            elif current_state == "processing":
                target_level = 0.35 + 0.25 * math.sin(tick * 0.25)
            else:
                target_level = 0.0
            for i, item in enumerate(bar_items):
                wobble = 0.75 + 0.25 * math.sin(tick * 0.35 + i * 0.7)
                target_h = ob.BAR_MIN_H + (ob.BAR_MAX_H - ob.BAR_MIN_H) * min(1.0, target_level * wobble)
                bar_heights[i] += (target_h - bar_heights[i]) * 0.35
                half_h = bar_heights[i] / 2
                cx = bars_x0 + i * (ob.BAR_W + ob.BAR_GAP) + ob.BAR_W / 2
                canvas.coords(item, cx - ob.BAR_W / 2, H / 2 - half_h, cx + ob.BAR_W / 2, H / 2 + half_h)
                canvas.itemconfig(item, fill=current_color)

        def poll():
            nonlocal visible, current_state, current_color
            try:
                while True:
                    cmd, payload = self._queue.get_nowait()
                    if cmd == "show":
                        state, profile = payload
                        current_state = state
                        current_color = ob.OVERLAY_STATE_COLOR.get(state, ob.OVERLAY_STATE_COLOR["recording"])
                        text = ob.OVERLAY_STATE_TEXT.get(state, ob.OVERLAY_STATE_TEXT["recording"])
                        if profile:
                            text += f" ({ob.OVERLAY_PROFILE_TEXT.get(profile, profile)})"
                        canvas.itemconfig(label, text=text)
                        canvas.itemconfig(dot, fill=current_color)
                        if not visible:
                            root.deiconify()
                            visible = True
                    elif cmd == "hide" and visible:
                        root.withdraw()
                        visible = False
                        for i in range(ob.BAR_COUNT):
                            bar_heights[i] = float(ob.BAR_MIN_H)
            except _queue.Empty:
                pass
            if visible:
                redraw_bars()
            root.after(40, poll)

        root.after(40, poll)
        root.mainloop()
