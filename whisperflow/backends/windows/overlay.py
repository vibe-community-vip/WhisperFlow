# -*- coding: utf-8 -*-
"""Overlay flotante en Windows: colorkey (``-transparentcolor``) + WS_EX_NOACTIVATE.

La animación y el dibujo son compartidos (``core/overlay_base.py`` +
``core/overlay_render.py``); acá solo queda lo específico de Windows.
"""
from whisperflow.core import overlay_base as ob


class WindowsOverlayBackend(ob.TkOverlayBase):
    def _configure_window(self, root, tk):
        try:
            root.attributes("-toolwindow", True)
        except Exception:
            pass

        # OJO: nada de -alpha. Windows renderiza con ClearType (sub-pixel, asume un
        # fondo sólido conocido); -alpha vuelve la ventana translúcida de verdad y
        # rompe ese supuesto. -transparentcolor no tiene ese problema: sus píxeles
        # son 100% opacos o 100% invisibles, nunca mezcla. Por eso el render aplana
        # la imagen sobre un KEY_COLOR casi negro (ver overlay_render).
        try:
            root.attributes("-transparentcolor", ob.KEY_COLOR_HEX)
        except Exception:
            pass

        root.update_idletasks()
        # WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW: la ventana nunca le roba el foco al
        # campo de texto donde se está dictando, ni aparece en la barra de tareas/Alt+Tab.
        try:
            import win32gui, win32con
            hwnd = root.winfo_id()
            exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   exstyle | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
        except Exception as e:
            print(f"[whisperflow] overlay sin WS_EX_NOACTIVATE ({e}); puede robar foco", flush=True)
