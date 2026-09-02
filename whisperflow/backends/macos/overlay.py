# -*- coding: utf-8 -*-
"""Overlay flotante en macOS: tkinter + ``-alpha`` (no hay colorkey fuera de Windows).

Diferencia visual aceptada frente a Windows: **esquinas cuadradas**. Sin colorkey no
se puede volver invisible el área fuera de la cápsula; el render aplana la imagen
sobre un casi-negro, así que ese marco se confunde con el cuerpo oscuro de la píldora.

THREADING (importante, descubierto al probar en Mac real): en macOS, ``tk.Tk()``
**debe crearse en el hilo principal y ANTES de que pystray inicialice NSApplication**;
si Cocoa se inicializa primero, Tk crashea con
``-[NSApplication macOSVersion]: unrecognized selector``. Por eso este backend
sobreescribe ``start``/``run_mainloop`` en vez de usar el hilo propio de la base:
  - ``start()`` construye el Tk en el hilo que lo llama (el principal, desde
    ``Application.__init__``), sin arrancar el mainloop.
  - ``run_mainloop()`` corre ``root.mainloop()`` bloqueando el hilo principal,
    mientras pystray corre ``run_detached()`` en el suyo.
"""
from whisperflow.core import overlay_base as ob


class MacOSOverlayBackend(ob.TkOverlayBase):
    def start(self):
        self._build()          # en el hilo principal; sin mainloop todavía

    def run_mainloop(self):
        if self._root is not None:
            self._root.mainloop()

    def _configure_window(self, root, tk):
        try:
            root.attributes("-alpha", 0.96)   # Mac permite -alpha (sin problema ClearType)
        except Exception:
            pass
