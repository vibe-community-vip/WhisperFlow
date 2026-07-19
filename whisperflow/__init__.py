# -*- coding: utf-8 -*-
"""WhisperFlow local — paquete multiplataforma.

Migración incremental (rama ``refactor/cross-platform``) del monolito
``whisperflow.py`` a un paquete con núcleo compartido (``core/``) y backends por
sistema operativo (``backends/``). ``whisperflow.py`` queda como shim de
compatibilidad para no romper el comando de ejecución existente.
"""
