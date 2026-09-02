# -*- coding: utf-8 -*-
"""whisperflow.py — Dictado por voz local, offline, sin suscripción (reemplazo de Wispr Flow).

Shim de compatibilidad: el código vive ahora en el paquete ``whisperflow/``. Este
archivo conserva el comando de ejecución original (``python whisperflow.py``) y sirve
de documentación de los atajos.

Atajos:
  - Ctrl + Win           -> push-to-talk puro: habla mientras sostienes ambas teclas;
                            al soltar cualquiera de las dos, transcribe y pega.
  - Ctrl + Win + Espacio -> modo "manos libres": sigue grabando aunque sueltes las
                            teclas. Suena UN bip distinto (más grave) al de
                            push-to-talk. Para detener y transcribir, vuelve a
                            presionar Ctrl+Win (no hace falta tocar Espacio otra vez)
                            o repite Ctrl+Win+Espacio. Si ya estabas en push-to-talk y
                            agregas Espacio a mitad, la grabación asciende a manos
                            libres sin perder el audio ya capturado.
  - Ctrl + Alt + Z       -> vuelve a pegar el último texto transcrito (por si no había
                            campo con foco donde cayó el pegado), igual que Wispr Flow.
                            Si lo presionas varias veces seguidas SIN dictar nada nuevo
                            en medio, retrocede a la grabación anterior (hasta las
                            últimas 3). Dictar algo nuevo reinicia el ciclo a la más
                            reciente. Este historial se guarda en disco
                            (last_recordings.json), así que sobrevive a reinicios de
                            la app.

No hay modos ni perfiles de tono: lo que dictas es lo que se pega.

El micrófono queda armado desde que arranca la app, así que la grabación empieza
exactamente cuando pulsas el atajo (y rescata los ~350 ms previos). Ver
``core/recorder.py``.

Motor: faster-whisper, modelo "medium" por defecto, español; GPU (CUDA) si está
disponible con fallback automático a CPU. El texto se pega en el campo con foco vía
portapapeles + Ctrl+V.
"""
from whisperflow.app import main

if __name__ == "__main__":
    main()
