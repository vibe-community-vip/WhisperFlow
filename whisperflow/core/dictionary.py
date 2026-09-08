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

Los tres NO usan la misma lista. La pista (1) incluye términos **y** destinos de
alias, porque ahí sumar vocabulario es gratis. La corrección difusa (3) usa **solo
los términos escritos explícitamente**: un destino de alias no debe disparar
reemplazos por parecido, y meterlos era una fuente silenciosa de texto destrozado.

**Dos archivos, a propósito**: ``dictionary.example.txt`` es la plantilla que se
versiona, y ``dictionary.txt`` es el diccionario real del usuario, que NO se versiona
(está en ``.gitignore``). El diccionario personal se llena de nombres de clientes,
proyectos y jerga propia, y este repo es público: separarlos evita publicarlos por
accidente. Si ``dictionary.txt`` no existe se lee la plantilla, así que un clon recién
bajado funciona igual.

El archivo se relee en cada dictado, así que se puede editar sin reiniciar.

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
DICTIONARY_PATH = os.path.join(PROJECT_ROOT, "dictionary.txt")           # el tuyo (git-ignored)
DICTIONARY_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, "dictionary.example.txt")  # plantilla versionada

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
MULTI_WORD_THRESHOLD = 0.68   # umbral de similitud GLOBAL para frases de varias palabras

# Segundo filtro para frases, y el que de verdad evita los desastres: además de
# parecerse en conjunto, CADA palabra de la ventana tiene que parecerse a la palabra
# correspondiente del término.
#
# Por qué hace falta: la similitud global sola no distingue una corrección legítima de
# un destrozo. Medido con un diccionario real de 92 términos, "wuspr floe" -> "Wispr
# Flow" (correcto) da 0.800 y "es segunda" -> "en seguida" (destrozo) da 0.800 TAMBIÉN:
# los rangos se solapan y no existe ningún umbral global que los separe. El resultado
# era que frases perfectas se reescribían — "la segunda idea" se convertía en "en
# seguida idea", "Claude hace" en "Claude Code" — porque una palabra muy parecida
# arrastraba a la otra que no se parecía en nada.
#
# Palabra por palabra sí separan limpio: las correcciones legítimas dan mínimos de
# 0.75-1.00 y los falsos positivos de 0.00-0.50 ("la" vs "en" = 0.0). 0.65 cae en ese
# hueco. Intuición: si de verdad dijiste el término, el modelo lo escribió mal letra a
# letra en cada palabra, no reemplazó una palabra entera por otra sin relación.
WORD_ALIGN_THRESHOLD = 0.65

# Frases de uso común que NO deben usarse como término. El diccionario existe para
# nombres propios y jerga que el modelo no conoce; una frase corriente del español
# como "en seguida" no aporta nada al modelo y en cambio ATRAE hacia sí cualquier
# otra frase corriente parecida. Caso real: con "en seguida" en el diccionario,
# "en segundo lugar" salía como "en seguida lugar" (global 0.800, por palabra 1.00 y
# 0.714: pasa los dos filtros). No hay umbral que lo arregle sin perder correcciones
# legítimas — "wuspr floe" -> "Wispr Flow" también da 0.750 por palabra.
#
# Regla: si un término de varias palabras es todo minúsculas y arranca con una
# palabra funcional, es una frase común, no vocabulario. Se avisa y se excluye de la
# corrección difusa. Sigue yendo al initial_prompt, que es inofensivo.
_PALABRAS_FUNCIONALES = {
    "a", "al", "ante", "con", "de", "del", "desde", "el", "en", "entre", "es", "esa",
    "ese", "esta", "este", "hacia", "hasta", "la", "las", "lo", "los", "mas", "más",
    "me", "mi", "no", "o", "para", "pero", "por", "que", "qué", "se", "si", "sí",
    "sin", "sobre", "su", "te", "tu", "un", "una", "y", "ya",
}

SINGLE_WORD_THRESHOLD = 0.82  # umbral para palabras sueltas
MIN_WORD_LEN_FOR_FUZZY = 4    # palabras muy cortas no se corrigen (demasiado ambiguas)

# load_dictionary() corre en CADA dictado (el archivo se relee para poder editarlo sin
# reiniciar), así que el aviso de frases comunes se emite una sola vez por término.
_ya_avisados = set()


def active_dictionary_path():
    """Ruta del diccionario que se va a leer: el personal si existe, si no la
    plantilla. Nunca crea archivos (esto corre en cada dictado)."""
    if os.path.exists(DICTIONARY_PATH):
        return DICTIONARY_PATH
    if os.path.exists(DICTIONARY_EXAMPLE_PATH):
        return DICTIONARY_EXAMPLE_PATH
    return None


def load_dictionary():
    """Devuelve (terms, aliases): terms = vocabulario plano; aliases = lista de
    (texto_mal_transcrito, texto_correcto) definidos con la sintaxis 'mal=>bien'."""
    terms, aliases = [], []
    path = active_dictionary_path()
    if path is None:
        return terms, aliases
    try:
        # utf-8-sig: si el archivo se editó con el Bloc de notas puede traer BOM,
        # y con utf-8 puro el primer término del diccionario quedaría corrupto.
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=>" in line:
                    wrong, correct = line.split("=>", 1)
                    wrong, correct = wrong.strip(), correct.strip()
                    if wrong and correct:
                        aliases.append((wrong, correct))
                        # OJO: el destino del alias NO se agrega a ``terms``. Antes sí,
                        # y era una fuente silenciosa de destrozos: el alias ya hace el
                        # reemplazo exacto, pero al colarse en la corrección difusa el
                        # destino empezaba a atraer texto parecido. Auditando un
                        # diccionario real, 27 términos habían entrado así sin que el
                        # usuario los escribiera nunca — incluidos "son" (de
                        # "Soon => son"), "genera", "adjunta", "leads" y "dime si", todas
                        # palabras corrientes del español. Si querés que un destino
                        # TAMBIÉN se corrija por parecido, escribilo aparte como término.
                elif line not in terms:
                    terms.append(line)
    except Exception as e:
        print(f"[whisperflow] no se pudo leer {os.path.basename(path)}: {e}", flush=True)
    nuevos = [t for t in terms if es_frase_comun(t) and t not in _ya_avisados]
    if nuevos:
        _ya_avisados.update(nuevos)
        print(f"[whisperflow] estos términos de dictionary.txt parecen frases comunes y "
              f"NO se usarán para corregir (atraerían hacia sí frases parecidas y "
              f"empeorarían el dictado): {', '.join(repr(t) for t in nuevos)}. Si lo que "
              f"querés es cambiar una cosa por otra, usá un alias: 'mal => bien'.",
              flush=True)
    return terms, aliases


def build_initial_prompt(terms, aliases=()):
    """Pista de vocabulario para el modelo.

    Incluye los destinos de los alias además de los términos: como pista son útiles
    (le dicen al modelo qué palabras esperar) y son inofensivos, a diferencia de la
    corrección difusa, de la que se los excluye a propósito (ver ``load_dictionary``)."""
    vocabulario = list(terms)
    for _mal, bien in aliases:
        if bien not in vocabulario:
            vocabulario.append(bien)
    if not vocabulario:
        return None
    prompt = "Vocabulario y términos técnicos relevantes: " + ", ".join(vocabulario) + "."
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


def es_frase_comun(term):
    """¿El término parece una frase corriente del idioma en vez de vocabulario?

    Todo minúsculas + empieza por palabra funcional => frase común. Deja pasar
    "prompt engineering" o "fine-tuning" (sin palabra funcional al inicio) y a
    cualquier cosa con mayúscula, guion o dígito ("Claude Code", "n8n", "large-v3")."""
    palabras = term.split()
    if len(palabras) < 2:
        return False
    if term != term.lower():
        return False                      # tiene mayúsculas: es un nombre propio
    if any(ch.isdigit() or ch == "-" for ch in term):
        return False
    return palabras[0] in _PALABRAS_FUNCIONALES


def _words_align(window, term):
    """¿Cada palabra de ``window`` se parece a la palabra correspondiente de ``term``?

    Es el filtro que evita que una palabra muy parecida arrastre a otra que no lo es
    (ver ``WORD_ALIGN_THRESHOLD``). Si los recuentos de palabras no coinciden, no hay
    correspondencia que comprobar y se rechaza."""
    w_words, t_words = window.split(), term.split()
    if len(w_words) != len(t_words):
        return False
    for w, t in zip(w_words, t_words):
        if difflib.SequenceMatcher(None, w.lower(), t.lower()).ratio() < WORD_ALIGN_THRESHOLD:
            return False
    return True


def apply_dictionary_corrections(text, terms):
    if not terms or not text:
        return text

    multi_terms = sorted((t for t in terms if " " in t and not es_frase_comun(t)),
                         key=lambda t: -len(t.split()))
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
            if ratio >= MULTI_WORD_THRESHOLD and core != term \
                    and _words_align(core, term):
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
