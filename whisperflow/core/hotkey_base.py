# -*- coding: utf-8 -*-
"""Hotkeys globales (interfaz + capacidades).

Cada backend envuelve la lib nativa del OS y emite eventos al orquestador. La
decisión de *cuándo* grabar vive en ``app.py`` (máquina de estados), no aquí.

Convención de ``register_suppressible_key``: el callback devuelve ``True`` para
dejar pasar la tecla al campo con foco, ``False`` para tragársela. En backends
donde ``capabilities().suppress_supported`` sea ``False`` (p.ej. Mac v1), el
callback igualmente se invoca pero el valor de retorno se ignora (la tecla pasa).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class HotkeyCapabilities:
    suppress_supported: bool   # False en Mac v1
    send_supported: bool       # inyección sintética (pegado la necesita)
    observe_all_keys: bool


class HotkeyBackend(ABC):
    @abstractmethod
    def start(self, on_event) -> None: ...
    @abstractmethod
    def register_suppressible_key(self, key: str, handler) -> None: ...
    @abstractmethod
    def register_hotkey(self, combo: str, callback) -> None: ...
    @abstractmethod
    def send(self, combo: str) -> None: ...
    @abstractmethod
    def release(self, key: str) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def capabilities(self) -> HotkeyCapabilities: ...
