# -*- coding: utf-8 -*-
"""Audita ``dictionary.txt`` buscando entradas que empeoran el dictado.

El diccionario es un arma de doble filo: un término bien elegido corrige un nombre
propio que el modelo no conoce, pero uno mal elegido **atrae hacia sí** frases
correctas y las destroza. Como se aplica en cada dictado y en silencio, esos daños
son difíciles de atribuir — parece que "el modelo transcribe mal".

Este script hace dos cosas:

1. **Revisión estructural**: alias duplicados o en conflicto, mayúsculas
   inconsistentes, términos que son frases corrientes, términos demasiado cortos
   que pueden capturar palabras comunes, y los que se quedan fuera del
   ``initial_prompt``.

2. **Prueba contra tu propio historial** (``transcripciones.md``), que es la parte
   que de verdad encuentra cosas: aplica el diccionario a tus dictados pasados y
   reporta **cada cambio**. Si el diccionario modifica texto que ya estaba bien, es
   un falso positivo — y ahí se ve con nombre y apellido.

Uso::

    python scripts/auditar_diccionario.py
    python scripts/auditar_diccionario.py --historial otro_archivo.md
"""
import argparse
import difflib
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whisperflow.core import dictionary as D  # noqa: E402

# Palabras españolas frecuentes: si un término coincide con una de estas, la
# corrección difusa puede engancharse a texto normal.
COMUNES = {
    "son", "ser", "esta", "este", "como", "para", "por", "que", "con", "una", "uno",
    "más", "mas", "pero", "todo", "toda", "hace", "hacer", "dice", "decir", "dime",
    "vamos", "quiero", "puede", "tiene", "ahora", "bien", "algo", "cosa", "parte",
    "forma", "modo", "caso", "vez", "año", "día", "hora", "gente", "agente", "guion",
    "generar", "genera", "merge", "sobre", "entre", "hasta", "desde", "cuando",
    "donde", "porque", "también", "solo", "sólo", "otro", "otra", "mismo", "misma",
}


def cargar_historial(path):
    """Extrae los textos de un transcripciones.md (bloques '> ' bajo cada '### ')."""
    if not os.path.exists(path):
        return []
    textos, actual = [], []
    with open(path, encoding="utf-8-sig") as f:
        for linea in f:
            if linea.startswith("### "):
                if actual:
                    textos.append(" ".join(actual).strip())
                    actual = []
            elif linea.startswith("> "):
                actual.append(linea[2:].strip())
    if actual:
        textos.append(" ".join(actual).strip())
    return [t for t in textos if t]


def diferencias(antes, despues):
    """Pares (fragmento_original, fragmento_nuevo) de lo que cambió."""
    a, b = antes.split(), despues.split()
    cambios = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag != "equal":
            cambios.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return cambios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--historial", default=None,
                    help="ruta a transcripciones.md (default: la del proyecto)")
    args = ap.parse_args()

    ruta = D.active_dictionary_path()
    if not ruta:
        sys.exit("No hay diccionario que auditar.")
    terms, aliases = D.load_dictionary()
    print(f"\nDiccionario: {ruta}")
    print(f"{len(terms)} términos · {len(aliases)} alias\n")

    problemas = 0

    # ---------- 1. Revisión estructural ----------
    print("=" * 72)
    print("REVISIÓN ESTRUCTURAL")
    print("=" * 72)

    # Alias con el mismo lado izquierdo apuntando a cosas distintas.
    por_origen = defaultdict(list)
    for mal, bien in aliases:
        por_origen[mal.lower()].append(bien)
    for mal, destinos in por_origen.items():
        if len(set(destinos)) > 1:
            problemas += 1
            print(f"  CONFLICTO  '{mal}' apunta a {destinos} — gana el último aplicado")
        elif len(destinos) > 1:
            problemas += 1
            print(f"  duplicado  '{mal} => {destinos[0]}' está repetido")

    # Mismo destino escrito de formas distintas.
    por_destino = defaultdict(set)
    for _mal, bien in aliases:
        por_destino[bien.lower()].add(bien)
    for clave, formas in por_destino.items():
        if len(formas) > 1:
            problemas += 1
            print(f"  MAYÚSCULAS inconsistentes: {sorted(formas)} — elegí una sola grafía")

    # Términos repetidos salvo por mayúsculas.
    cuenta = Counter(t.lower() for t in terms)
    for clave, n in cuenta.items():
        if n > 1:
            formas = [t for t in terms if t.lower() == clave]
            problemas += 1
            print(f"  duplicado  {formas} difieren solo en mayúsculas")

    # El lado izquierdo de un alias que además es término: se corrige y se
    # "descorrige", o el alias nunca llega a aplicarse como esperabas.
    terms_lower = {t.lower() for t in terms}
    for mal, bien in aliases:
        if mal.lower() in terms_lower and mal.lower() != bien.lower():
            problemas += 1
            print(f"  AMBIGUO    '{mal}' es alias (=> {bien}) Y término a la vez")

    # Frases comunes: el guardarraíl ya las excluye, pero conviene saberlo.
    comunes = [t for t in terms if D.es_frase_comun(t)]
    for t in comunes:
        problemas += 1
        print(f"  IGNORADO   '{t}' parece frase común: NO se usa para corregir")

    # Términos que son palabras corrientes del español.
    for t in terms:
        if " " not in t and t.lower() in COMUNES:
            problemas += 1
            print(f"  RIESGOSO   '{t}' es una palabra común: puede capturar texto normal")

    # Términos cortos que pueden tragarse palabras más largas.
    for t in terms:
        if " " not in t and len(t) < 5 and t.lower() not in COMUNES:
            riesgo = [p for p in COMUNES
                      if len(p) >= D.MIN_WORD_LEN_FOR_FUZZY
                      and difflib.SequenceMatcher(None, p, t.lower()).ratio() >= D.SINGLE_WORD_THRESHOLD]
            if riesgo:
                problemas += 1
                print(f"  RIESGOSO   '{t}' es muy corto y se parece a {riesgo}")

    # Lo que no entra en el initial_prompt.
    completo = "Vocabulario y términos técnicos relevantes: " + ", ".join(terms) + "."
    if len(completo) > D.MAX_PROMPT_CHARS:
        recortado = D.build_initial_prompt(terms)
        dentro = recortado.count(",")
        print(f"\n  El initial_prompt se recorta en {D.MAX_PROMPT_CHARS} de {len(completo)} "
              f"caracteres: solo los primeros ~{dentro} términos llegan al modelo como")
        print(f"  pista. Los demás siguen corrigiendo DESPUÉS, pero el modelo no los")
        print(f"  anticipa. Poné arriba los que más te importa que acierte de una.")

    if problemas == 0:
        print("  sin problemas estructurales.")

    # ---------- 2. Contra tu propio historial ----------
    hist = args.historial or os.path.join(D.PROJECT_ROOT, "transcripciones.md")
    textos = cargar_historial(hist)
    print()
    print("=" * 72)
    print("PRUEBA CONTRA TU HISTORIAL")
    print("=" * 72)
    if not textos:
        print(f"  no se encontró historial en {hist}")
        return
    print(f"  {len(textos)} dictados pasados en {os.path.basename(hist)}\n")

    culpables = defaultdict(list)
    for texto in textos:
        salida = D.apply_dictionary_corrections(D.apply_aliases(texto, aliases), terms)
        if salida == texto:
            continue
        for orig, nuevo in diferencias(texto, salida):
            if orig.lower() != nuevo.lower():
                culpables[nuevo].append(orig)

    if not culpables:
        print("  el diccionario no altera ninguno de tus dictados pasados.")
        return

    print("  Cambios que el diccionario haría sobre texto que YA habías dictado.")
    print("  Revisá cada uno: si el original estaba bien, es un falso positivo.\n")
    for nuevo, originales in sorted(culpables.items(), key=lambda kv: -len(kv[1])):
        ejemplos = Counter(originales)
        detalle = ", ".join(f"{o!r} (x{n})" if n > 1 else f"{o!r}"
                            for o, n in ejemplos.most_common(6))
        print(f"  -> {nuevo!r}  reemplazaría a: {detalle}")

    print()
    print("  Para quitar un falso positivo: borrá ese término de dictionary.txt. Si lo")
    print("  que querías era cambiar una cosa concreta por otra, usá un alias exacto")
    print("  ('mal => bien'), que no se dispara por parecido.")


if __name__ == "__main__":
    main()
