# -*- coding: utf-8 -*-
"""Diccionario de precisión para la transcripción (núcleo multiplataforma).

Tres mecanismos, igual que Wispr Flow y apps similares:
  1. ``initial_prompt`` de faster-whisper: le da al modelo una lista de términos
     esperados ANTES de transcribir, sesgando la decodificación hacia ellos.
  2. Alias exactos (``mal => bien``): reemplazo literal, para errores que Whisper
     comete siempre igual (ej. ``clod => Claude``).
  3. Corrección difusa post-transcripción: si Whisper escribió algo parecido pero
     no exacto a un término, se reemplaza por la grafía correcta (comparando
     similitud de texto, tolera errores fonéticos leves).

``dictionary.txt`` se relee en cada dictado, así que se puede editar sin reiniciar.

Este módulo es deliberadamente puro (solo stdlib: ``os``/``re``/``string``/
``difflib``) para poder ejecutarse y testearse en cualquier plataforma, incluido
el harness de caracterización (``scripts/characterize.py``) que corre en macOS.
"""
import os
import re
import difflib
import string

# Raíz del proyecto = <project>/ (este archivo está en <project>/whisperflow/core/).
# Antes esto era SCRIPT_DIR = dirname(abspath(__file__)) dentro de whisperflow.py
# (que vive en la raíz); aquí calculamos la misma raíz subiendo tres niveles.
_HERE = os.path.dirname(os.path.abspath(__file__))      # .../whisperflow/core
_PKG = os.path.dirname(_HERE)                            # .../whisperflow
PROJECT_ROOT = os.path.dirname(_PKG)                     # <project>
DICTIONARY_PATH = os.path.join(PROJECT_ROOT, "dictionary.txt")

# Tope del initial_prompt. OJO, es un límite real y se alcanza rápido: Whisper
# reserva ~224 tokens para el prompt, así que un diccionario grande NO entra entero
# (medido con un dictionary.txt de 92 términos: el prompt daba 949 chars y se
# recortan los últimos ~15 términos). Eso NO los deja sin efecto: la corrección
# difusa de más abajo se aplica a TODOS los términos después de transcribir, y es
# la que hace el trabajo pesado. El initial_prompt solo sesga la decodificación.
# Conclusión práctica: poné primero en dictionary.txt los términos que más te
# importa que el modelo acierte "de una", y usá alias (``mal => bien``) para los
# errores que se repiten siempre igual.
MAX_PROMPT_CHARS = 800
MULTI_WORD_THRESHOLD = 0.68   # umbral de similitud para frases de varias palabras
SINGLE_WORD_THRESHOLD = 0.82  # umbral más exigente para palabras sueltas (más riesgo de falso positivo)
MIN_WORD_LEN_FOR_FUZZY = 4    # palabras muy cortas no se corrigen (demasiado ambiguas)


def load_dictionary():
    """Devuelve (terms, aliases): terms = vocabulario plano; aliases = lista de
    (texto_mal_transcrito, texto_correcto) definidos con la sintaxis 'mal=>bien'."""
    terms, aliases = [], []
    if not os.path.exists(DICTIONARY_PATH):
        return terms, aliases
    try:
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=>" in line:
                    wrong, correct = line.split("=>", 1)
                    wrong, correct = wrong.strip(), correct.strip()
                    if wrong and correct:
                        aliases.append((wrong, correct))
                        if correct not in terms:
                            terms.append(correct)
                elif line not in terms:
                    terms.append(line)
    except Exception as e:
        print(f"[whisperflow] no se pudo leer dictionary.txt: {e}", flush=True)
    return terms, aliases


def build_initial_prompt(terms):
    if not terms:
        return None
    prompt = "Vocabulario y términos técnicos relevantes: " + ", ".join(terms) + "."
    return prompt[:MAX_PROMPT_CHARS]


def apply_aliases(text, aliases):
    for wrong, correct in aliases:
        pattern = re.compile(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)", re.IGNORECASE)
        text = pattern.sub(correct, text)
    return text


def _strip_punct(word):
    lead = ""
    i = 0
    while i < len(word) and word[i] in string.punctuation:
        lead += word[i]
        i += 1
    trail = ""
    j = len(word) - 1
    while j >= i and word[j] in string.punctuation:
        trail = word[j] + trail
        j -= 1
    core = word[i:j + 1] if j >= i else ""
    return lead, core, trail


def apply_dictionary_corrections(text, terms):
    if not terms or not text:
        return text

    multi_terms = sorted((t for t in terms if " " in t), key=lambda t: -len(t.split()))
    single_terms = [t for t in terms if " " not in t]
    words = text.split(" ")

    # 1) Frases de varias palabras: ventana deslizante del mismo número de palabras.
    merged = []
    i = 0
    while i < len(words):
        matched = None
        for term in multi_terms:
            n = len(term.split())
            if i + n > len(words):
                continue
            window = " ".join(words[i:i + n])
            _, core, trail = _strip_punct(window)
            ratio = difflib.SequenceMatcher(None, core.lower(), term.lower()).ratio()
            if ratio >= MULTI_WORD_THRESHOLD and core != term:
                matched = (term, n, trail)
                break
        if matched:
            term, n, trail = matched
            merged.append(term + trail)
            i += n
        else:
            merged.append(words[i])
            i += 1

    # 2) Palabras sueltas: comparación difusa individual contra el diccionario.
    result = []
    for w in merged:
        lead, core, trail = _strip_punct(w)
        if len(core) < MIN_WORD_LEN_FOR_FUZZY:
            result.append(w)
            continue
        best_term, best_ratio = None, 0.0
        for term in single_terms:
            r = difflib.SequenceMatcher(None, core.lower(), term.lower()).ratio()
            if r > best_ratio:
                best_ratio, best_term = r, term
        if best_term and best_ratio >= SINGLE_WORD_THRESHOLD and core != best_term:
            result.append(lead + best_term + trail)
        else:
            result.append(w)
    return " ".join(result)
