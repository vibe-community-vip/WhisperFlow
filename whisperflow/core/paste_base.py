# -*- coding: utf-8 -*-
"""Pegado en el campo con foco (interfaz).

Cada backend es dueño de sus rarezas de plataforma:
  - Windows: liberar alt/z antes de ctrl+v, pyperclip + keyboard.send("ctrl+v"),
    espacio final ``text + " "``, restaurar el portapapeles previo a los 0.6 s.
  - Mac: pbcopy + cmd+v (CGEvent).  Linux: xclip+xdotool / wl-copy+wtype.
"""
from abc import ABC, abstractmethod


class PasteBackend(ABC):
    @abstractmethod
    def paste(self, text: str) -> None: ...
