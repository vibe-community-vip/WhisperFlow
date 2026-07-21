# -*- coding: utf-8 -*-
"""Overlay flotante en Windows: tkinter + win32gui (WS_EX_NOACTIVATE) + transparentcolor."""
import math
import queue as _queue
import threading

from whisperflow.core import overlay_base as ob
from whisperflow.core import recorder


class WindowsOverlayBackend(ob.OverlayBackend):
    """Píldora flotante abajo al centro, con mini-ecualizador. Hilo propio + Tk propio;
    los comandos llegan por cola (nunca tocar widgets desde otro hilo). NUNCA usar
    ``-alpha``: combina mal con el ClearType de Windows (flecos de color). Solo
    ``-transparentcolor`` (colorkey binario) para las esquinas redondeadas."""

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
        # El hilo es daemon con su propio mainloop; el os._exit(0) del orquestador
        # termina todo el proceso. No hay forma limpia de cortar mainloop desde aquí.
        pass

    def _run(self):
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass
        # OJO: nada de -alpha aquí. Windows renderiza el texto con ClearType (sub-pixel,
        # asume un fondo sólido conocido); -alpha vuelve la ventana translúcida de verdad
        # y rompe ese supuesto -> texto con flecos de color. -transparentcolor (abajo) no
        # tiene ese problema: sus pixeles son 100% opacos o 100% invisibles, nunca mezcla.

        W, H = ob.PILL_W, ob.PILL_H
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - 110}")

        # bg=magenta + transparentcolor: el canvas de fondo se vuelve invisible y solo
        # se ve la píldora redondeada, en vez de un rectángulo cuadrado.
        root.config(bg="#ff00ff")
        try:
            root.attributes("-transparentcolor", "#ff00ff")
        except Exception:
            pass

        canvas = tk.Canvas(root, width=W, height=H, bg="#ff00ff", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        pill = canvas.create_polygon(
            ob.rounded_rect_points(1, 1, W - 1, H - 1, ob.PILL_RADIUS),
            smooth=True, fill="#232328", outline="#8ecae6", width=1.5)

        dot_cx = ob.PAD_LEFT + ob.DOT_RADIUS
        dot = canvas.create_oval(dot_cx - ob.DOT_RADIUS, H / 2 - ob.DOT_RADIUS,
                                 dot_cx + ob.DOT_RADIUS, H / 2 + ob.DOT_RADIUS,
                                 fill="#8ecae6", outline="")

        text_x = dot_cx + ob.DOT_RADIUS + 7
        label = canvas.create_text(text_x, H // 2, text="", fill=ob.OVERLAY_TEXT_COLOR, anchor="w",
                                   font=("Segoe UI Semibold", 9))

        bars_x0 = W - ob.PAD_RIGHT - ob.BARS_AREA_W
        bar_items = []
        for i in range(ob.BAR_COUNT):
            cx = bars_x0 + i * (ob.BAR_W + ob.BAR_GAP) + ob.BAR_W / 2
            item = canvas.create_rectangle(cx - ob.BAR_W / 2, H / 2 - ob.BAR_MIN_H / 2,
                                           cx + ob.BAR_W / 2, H / 2 + ob.BAR_MIN_H / 2,
                                           fill="#8ecae6", outline="")
            bar_items.append(item)

        root.update_idletasks()
        # WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW: la ventana nunca le roba el foco al campo
        # de texto donde se está dictando, ni aparece en la barra de tareas/Alt+Tab.
        try:
            import win32gui, win32con
            hwnd = root.winfo_id()
            exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   exstyle | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
        except Exception as e:
            print(f"[whisperflow] overlay sin WS_EX_NOACTIVATE ({e}); puede robar foco", flush=True)

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
                target_level = 0.35 + 0.25 * math.sin(tick * 0.25)  # pulso tranquilo, sin mic en vivo
            else:
                target_level = 0.0

            for i, item in enumerate(bar_items):
                wobble = 0.75 + 0.25 * math.sin(tick * 0.35 + i * 0.7)  # da vidilla a cada barra
                target_h = ob.BAR_MIN_H + (ob.BAR_MAX_H - ob.BAR_MIN_H) * min(1.0, target_level * wobble)
                bar_heights[i] += (target_h - bar_heights[i]) * 0.35  # suaviza
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
                        canvas.itemconfig(pill, outline=current_color)
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
