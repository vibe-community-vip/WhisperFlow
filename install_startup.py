# -*- coding: utf-8 -*-
"""
install_startup.py — Crea un acceso directo en la carpeta de Inicio de Windows
para que whisperflow.py arranque solo (en segundo plano, sin ventana de consola)
al iniciar sesión.

Uso:  python install_startup.py           (instala)
      python install_startup.py --remove  (desinstala)
"""
import os, sys, winshell
from win32com.client import Dispatch

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# dirname(sys.executable), no sys.exec_prefix: dentro de un venv de Windows, pythonw.exe
# vive en <venv>\Scripts\, pero sys.exec_prefix apunta a la raíz del venv (sin \Scripts),
# así que exec_prefix + "pythonw.exe" apuntaría a un archivo que no existe.
PYTHONW = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "pythonw.exe")
SCRIPT = os.path.join(PROJECT_DIR, "whisperflow.py")
SHORTCUT_NAME = "WhisperFlow local.lnk"


def startup_folder():
    return winshell.startup()


def install():
    shortcut_path = os.path.join(startup_folder(), SHORTCUT_NAME)
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = PYTHONW
    shortcut.Arguments = f'"{SCRIPT}"'
    shortcut.WorkingDirectory = PROJECT_DIR
    shortcut.IconLocation = PYTHONW
    shortcut.Description = "WhisperFlow local (Ctrl+Win+Espacio para dictar)"
    shortcut.save()
    print(f"Acceso directo creado: {shortcut_path}")
    print("WhisperFlow arrancará automáticamente en el próximo inicio de sesión.")


def remove():
    shortcut_path = os.path.join(startup_folder(), SHORTCUT_NAME)
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)
        print(f"Eliminado: {shortcut_path}")
    else:
        print("No había ningún acceso directo instalado.")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove()
    else:
        install()
