# -*- coding: utf-8 -*-
"""Filtro de alucinaciones conocidas de Whisper (última red antes de pegar).

Whisper se entrenó con muchísimo video de YouTube subtitulado por voluntarios, y
sobre audio mudo o de nivel muy bajo tiende a "recordar" los créditos que aparecían
al final de esos videos — en español, casi siempre *"Subtítulos realizados por la
comunidad de Amara.org"*. Es un bug documentado del modelo, no de esta app.

En el pipeline hay **cuatro** defensas contra esto, de más temprana a más tardía:

1. ``core/vad.py`` — descarta la captura entera si no tiene energía de voz, antes
   siquiera de llamar al modelo. Es la que más casos mata.
2. ``vad_filter=True`` en ``asr_ct2`` — el VAD interno de faster-whisper recorta los
   tramos mudos del audio que sí se transcribe.
3. ``condition_on_previous_text=False`` — sin arrastrar el texto ya decodificado, el
   modelo tiene mucho menos con qué alimentar el bucle.
4. Este módulo — reemplazo literal del crédito si aun así se cuela.

Nota sobre ``hallucination_silence_threshold`` (parámetro de faster-whisper): **solo
tiene efecto con** ``word_timestamps=True`` (está dentro de ese ``if`` en
``transcribe.py``). Pasarlo sin los timestamps de palabra, como se hacía antes, es
inerte; y activarlos cuesta cómputo extra en cada dictado. Con las cuatro defensas de
arriba no hace falta.

**Cuidado al agregar patrones**: esto se aplica a texto real dictado. Un patrón
demasiado amplio (p. ej. "gracias por ver") borraría frases legítimas. Solo van acá
frases largas y literales que el modelo emite palabra por palabra.
"""
import re

_PATTERNS = [
    re.compile(
        r"subt[ií]tulos?\s+(realizados?\s+)?por\s+la\s+comunidad\s+de\s+amara\.org"
        r"|subtitles?\s+by\s+the\s+amara\.org\s+community"
        r"|subtitles?\s+by\s+the\s+community\s+of\s+amara\.org",
        re.IGNORECASE,
    ),
]


def strip_known_hallucinations(text):
    """Quita créditos alucinados del texto. Si no hay nada que quitar devuelve el
    texto **intacto** (ni siquiera normaliza espacios: no queremos tocar la
    puntuación de un dictado real)."""
    if not text:
        return text
    cleaned = text
    for pattern in _PATTERNS:
        cleaned = pattern.sub("", cleaned)
    if cleaned == text:
        return text
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned
