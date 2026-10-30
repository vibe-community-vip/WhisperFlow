# -*- coding: utf-8 -*-
"""Overlay flotante en Windows: colorkey (``-transparentcolor``) + ``-alpha`` +
WS_EX_NOACTIVATE.

La animación y el dibujo son compartidos (``core/overlay_base.py`` +
``core/overlay_render.py``); acá solo queda lo específico de Windows.
"""
from whisperflow.core import config
from whisperflow.core import overlay_base as ob


class WindowsOverlayBackend(ob.TkOverlayBase):
    def _configure_window(self, root, tk):
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass

        # El colorkey vuelve invisible el KEY_COLOR casi negro de fuera de la cápsula
        # (esquinas redondeadas, ver overlay_render). -alpha se suma encima: Tk llama a
        # SetLayeredWindowAttributes con LWA_COLORKEY|LWA_ALPHA, y Windows aplica las
        # dos (verificado con captura real: esquinas redondeadas y texto de atrás
        # visible a través de la cápsula). Antes se evitaba -alpha por ClearType, pero
        # el texto ya lo rasteriza Pillow, no Tk.
        try:
            root.attributes("-transparentcolor", ob.KEY_COLOR_HEX)
        except Exception:
            pass
        if config.OVERLAY_OPACITY < 1.0:
            try:
                root.attributes("-alpha", config.OVERLAY_OPACITY)
            except Exception:
                pass

        root.update_idletasks()
        # WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW: la ventana nunca le roba el foco al
        # campo de texto donde se está dictando, ni aparece en la barra de tareas/Alt+Tab.
        # WS_EX_TRANSPARENT: los clics la atraviesan. Aparece junto al puntero, así que
        # sin esto un clic justo ahí caería sobre la cápsula en vez de en la app.
        try:
            import win32gui, win32con
            hwnd = root.winfo_id()
            exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   exstyle | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
            # winfo_id() es la ventana hija de Tk; el marco de nivel superior (el que
            # es "layered" y recibe los clics) es su ancestro raíz.
            frame = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
            exstyle = win32gui.GetWindowLong(frame, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(frame, win32con.GWL_EXSTYLE,
                                   exstyle | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW
                                   | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED)
        except Exception as e:
            print(f"[whisperflow] overlay sin WS_EX_NOACTIVATE ({e}); puede robar foco", flush=True)

    def _work_area(self, root, x, y):
        # Área útil (sin barra de tareas) del monitor donde está el puntero; la base
        # solo conoce la pantalla principal. Coordenadas físicas: el proceso es
        # DPI-aware (startup_init), igual que winfo_pointerxy.
        try:
            import win32api, win32con
            mon = win32api.MonitorFromPoint((x, y), win32con.MONITOR_DEFAULTTONEAREST)
            return win32api.GetMonitorInfo(mon)["Work"]
        except Exception:
            return super()._work_area(root, x, y)
