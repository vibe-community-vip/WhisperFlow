# -*- coding: utf-8 -*-
"""Ícono en la bandeja del sistema (núcleo multiplataforma, vía pystray).

Se separa ``build_icon`` de ``run_icon`` para que el orquestador pueda actualizar el
``title`` (tooltip) en vivo durante la carga perezosa del modelo (Fase 2).
"""
import pystray
from PIL import Image, ImageDraw


def make_icon_image():
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((14, 8, 50, 40), fill="white")
    d.rectangle((28, 40, 36, 52), fill="white")
    d.rectangle((18, 52, 46, 58), fill="white")
    return img


def build_icon(title: str, on_quit):
    """on_quit(icon, item) es el callback del ítem "Salir"; el orquestador es dueño
    del apagado (mantiene ``os._exit(0)`` — ver CLAUDE.md)."""
    return pystray.Icon("whisperflow", make_icon_image(), title,
                        menu=pystray.Menu(pystray.MenuItem("Salir", on_quit)))


def run_icon(icon):
    """Bloqueante: corre el loop de la bandeja en el hilo principal."""
    icon.run()
