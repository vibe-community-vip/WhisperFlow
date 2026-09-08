#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harness de caracterización para WhisperFlow.

Compara las salidas de las funciones PURAS y multiplataforma (el diccionario de
precisión y el filtro de alucinaciones) contra valores "golden" capturados antes. No es un test unitario
tradicional: es una red de seguridad para detectar regresiones silenciosas durante
la reingeniería (Fase 1), que de otro modo no podría verificarse en macOS porque
la app completa es Windows-only.

Uso (desde la raíz del proyecto):
    python3 scripts/characterize.py --update   # (re)captura los golden
    python3 scripts/characterize.py            # compara contra los golden (falla si hay diff)

Los golden viven en scripts/golden/. Como las funciones son determinísticas, el
resultado debe ser idéntico commit a commit salvo cambio intencional.
"""
import json
import os
import sys
import tempfile

# Asegurar que el paquete del proyecto es importable al correr desde la raíz.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from whisperflow.core import dictionary as D
from whisperflow.core import hallucinations as H

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")


def _cases():
    """Devuelve {nombre: resultado} con salidas de las funciones puras.
    Todas las entradas son fijas (no dependen del dictionary.txt del usuario)."""
    out = {}

    # --- build_initial_prompt ---
    out["build_initial_prompt(empty)"] = D.build_initial_prompt([])
    out["build_initial_prompt(few)"] = D.build_initial_prompt(["Claude", "LangChain", "RAG"])
    many = [f"termino{idx}" for idx in range(500)]
    prompt_many = D.build_initial_prompt(many)
    out["build_initial_prompt(many).len"] = len(prompt_many) if prompt_many else None
    out["build_initial_prompt(many).value"] = prompt_many

    # --- apply_aliases ---
    out["apply_aliases(none)"] = D.apply_aliases("hola mundo", [])
    out["apply_aliases(simple)"] = D.apply_aliases("uso clod todos los dias", [("clod", "Claude")])
    out["apply_aliases(case-insensitive)"] = D.apply_aliases("CLOD y Clod y clod", [("clod", "Claude")])
    out["apply_aliases(word-boundary)"] = D.apply_aliases("clodificar con clod", [("clod", "Claude")])
    out["apply_aliases(multiple)"] = D.apply_aliases("clod y sas", [("clod", "Claude"), ("sas", "SaaS")])

    # --- apply_dictionary_corrections (palabras sueltas) ---
    terms_single = ["Claude", "LangChain", "Anthropic", "OpenAI", "n8n", "RAG", "ai"]
    out["corrections(exact-noop)"] = D.apply_dictionary_corrections("Claude y LangChain", terms_single)
    out["corrections(fuzzy-single)"] = D.apply_dictionary_corrections("uso clod y lang-chain", terms_single)
    out["corrections(short-word-skip)"] = D.apply_dictionary_corrections("ai y ar no se corrigen", terms_single)
    out["corrections(punct)"] = D.apply_dictionary_corrections("(clod) es genial.", terms_single)
    out["corrections(empty)"] = D.apply_dictionary_corrections("", terms_single)

    # --- apply_dictionary_corrections (frases multi-palabra) ---
    terms_multi = ["Wispr Flow", "Claude Code", "Hugging Face", "faster-whisper"]
    out["corrections(multi-exact)"] = D.apply_dictionary_corrections("uso Wispr Flow y Claude Code", terms_multi)
    out["corrections(multi-fuzzy)"] = D.apply_dictionary_corrections("uso wuspr floe y claude kode", terms_multi)
    out["corrections(multi-prefix)"] = D.apply_dictionary_corrections("prueba faster whisper ahora", terms_multi)

    # Falsos positivos de la corrección por frase: texto CORRECTO que no se debe tocar.
    # Todos estos se destrozaban cuando el único filtro era la similitud global (0.68);
    # los atrapa el chequeo palabra por palabra (WORD_ALIGN_THRESHOLD). Reproducen un
    # caso real de uso diario, así que si alguien afloja ese filtro, esto lo avisa.
    terms_fp = ["en seguida", "Claude Code", "Wispr Flow"]
    out["corrections(fp-la-segunda)"] = D.apply_dictionary_corrections(
        "la segunda idea es un curso", terms_fp)
    out["corrections(fp-y-segunda)"] = D.apply_dictionary_corrections(
        "y segunda cosa que quiero", terms_fp)
    out["corrections(fp-es-segunda)"] = D.apply_dictionary_corrections(
        "es segunda vez que pasa", terms_fp)
    out["corrections(fp-claude-hace)"] = D.apply_dictionary_corrections(
        "lo que Claude hace por mi", terms_fp)
    # ...y la corrección legítima tiene que seguir ocurriendo con los MISMOS términos.
    out["corrections(fp-sigue-corrigiendo)"] = D.apply_dictionary_corrections(
        "uso wuspr floe a diario", terms_fp)

    # Guardarraíl de frases comunes: un término como "en seguida" NO debe usarse para
    # corregir. Caso real: convertía "en segundo lugar" en "en seguida lugar", y eso
    # pasa los dos filtros de similitud (global 0.800, por palabra 0.714) — hace falta
    # excluir el término, no ajustar umbrales.
    out["es_frase_comun(en seguida)"] = D.es_frase_comun("en seguida")
    out["es_frase_comun(de nuevo)"] = D.es_frase_comun("de nuevo")
    out["es_frase_comun(prompt engineering)"] = D.es_frase_comun("prompt engineering")
    out["es_frase_comun(Claude Code)"] = D.es_frase_comun("Claude Code")
    out["es_frase_comun(large-v3 turbo)"] = D.es_frase_comun("large-v3 turbo")
    out["es_frase_comun(RAG)"] = D.es_frase_comun("RAG")
    out["corrections(guardarrail-en-segundo)"] = D.apply_dictionary_corrections(
        "en segundo lugar quiero esto", ["en seguida"])

    # El destino de un alias NO entra en la corrección difusa (sí en la pista). Con
    # "Soon => son", "son" se volvía objetivo difuso y capturaba texto normal; en un
    # diccionario real habían entrado así 27 términos que el usuario nunca escribió.
    out["build_initial_prompt(con-alias)"] = D.build_initial_prompt(
        ["Claude"], [("clod", "Claude"), ("SAS", "SaaS")])
    out["build_initial_prompt(sin-alias)"] = D.build_initial_prompt(["Claude"])

    # --- load_dictionary (parse sobre un archivo temporal controlado) ---
    sample = (
        "# diccionario de prueba\n"
        "ChatGPT\n"
        "Claude\n"
        "Claude Code\n"
        "  # linea con indent y comentario\n"
        "clod => Claude\n"
        "SAS => SaaS\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(sample)
        tmp_path = tf.name
    try:
        orig = D.DICTIONARY_PATH
        D.DICTIONARY_PATH = tmp_path
        terms, aliases = D.load_dictionary()
        D.DICTIONARY_PATH = orig
    finally:
        os.unlink(tmp_path)
    out["load_dictionary(terms)"] = terms
    out["load_dictionary(aliases)"] = aliases

    # --- strip_known_hallucinations ---
    # Lo importante de estos casos es la ASIMETRÍA: si hay crédito alucinado se
    # limpia; si no lo hay, el texto tiene que volver intacto (puntuación incluida).
    out["hallucinations(none)"] = H.strip_known_hallucinations(
        "Gracias por ver el video, nos vemos mañana.")
    out["hallucinations(trailing)"] = H.strip_known_hallucinations(
        "Necesito revisar el deploy. Subtítulos realizados por la comunidad de Amara.org")
    out["hallucinations(only)"] = H.strip_known_hallucinations(
        "Subtítulos por la comunidad de Amara.org")
    out["hallucinations(english)"] = H.strip_known_hallucinations(
        "Subtitles by the Amara.org community")
    out["hallucinations(empty)"] = H.strip_known_hallucinations("")
    out["hallucinations(none-value)"] = H.strip_known_hallucinations(None)

    return out


def main():
    update = "--update" in sys.argv
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    golden_path = os.path.join(GOLDEN_DIR, "dictionary.json")
    actual = _cases()

    if update:
        with open(golden_path, "w", encoding="utf-8") as f:
            json.dump(actual, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"[characterize] golden escritos en {golden_path}")
        return 0

    if not os.path.exists(golden_path):
        print(f"[characterize] FALTA golden ({golden_path}). "
              f"Corré primero: python3 scripts/characterize.py --update")
        return 2

    with open(golden_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    def _stable(v):
        # Serializar a JSON para normalizar tupla vs lista y orden de claves:
        # load_dictionary devuelve tuplas, pero el golden (JSON) las guarda como listas.
        return json.dumps(v, sort_keys=True, ensure_ascii=False)

    diffs = []
    for key in sorted(set(actual) | set(expected)):
        a = actual.get(key, "<<MISSING>>")
        e = expected.get(key, "<<MISSING>>")
        if _stable(a) != _stable(e):
            diffs.append((key, e, a))

    if diffs:
        print(f"[characterize] {len(diffs)} diferencia(s) frente al golden:")
        for key, e, a in diffs:
            print(f"  - {key}\n      esperado: {e!r}\n      actual:   {a!r}")
        print("\nSi el cambio es intencional, actualizá el golden: "
              "python3 scripts/characterize.py --update")
        return 1

    print(f"[characterize] OK — {len(actual)} casos coinciden con el golden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
