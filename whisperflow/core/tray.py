# -*- coding: utf-8 -*-
"""Ícono en la bandeja del sistema (núcleo multiplataforma, vía pystray)."""
import pystray
from PIL import Image, ImageDraw


def make_icon_image():
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((14, 8, 50, 40), fill="white")
    d.rectangle((28, 40, 36, 52), fill="white")
    d.rectangle((18, 52, 46, 58), fill="white")
    return img


def run_tray(title: str, on_quit):
    """Bloqueante. ``on_quit(icon, item)`` es el callback del ítem "Salir"; el
    orquestador es dueño del apagado (mantiene ``os._exit(0)`` — ver CLAUDE.md)."""
    icon = pystray.Icon("whisperflow", make_icon_image(), title,
                        menu=pystray.Menu(pystray.MenuItem("Salir", on_quit)))
    icon.run()
