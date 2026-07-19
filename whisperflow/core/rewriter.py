# -*- coding: utf-8 -*-
"""Reescritura de tono vía LLM (núcleo multiplataforma).

Fase 1: solo OpenAI, idéntico al monolito original (degradación elegante: si no
hay ``OPENAI_API_KEY``, se pega el texto tal cual y se avisa una vez por consola).
Fase 3 agrega Ollama (local) + un selector con auto-detección.
"""
import os

OPENAI_MODEL = "gpt-4.1-nano"  # el más rápido/barato de OpenAI apto para reescribir texto corto

PROFILE_PROMPTS = {
    "friendly": (
        "Reescribe el siguiente texto dictado por voz para que suene amigable y cercano, "
        "como si le hablaras a un miembro de tu comunidad. Puedes cambiar signos de puntuación "
        "por signos de exclamación donde ya haya ese tono, y agregar como máximo 1 o 2 emojis "
        "que encajen con alguna palabra ya presente en el texto. "
        "PROHIBIDO: no agregues saludos, muletillas, oraciones, frases o ideas que no estén "
        "ya en el texto original; no expandas ni alargues el mensaje; no agregues ninguna "
        "palabra nueva que no sea un emoji. El número de palabras del resultado debe ser "
        "prácticamente el mismo que el del original (los emojis no cuentan como palabra). "
        "Corrige solo errores obvios de dictado. Conserva el idioma original. "
        "Responde ÚNICAMENTE con el texto reescrito, sin comillas ni explicaciones."
    ),
    "professional": (
        "Reescribe el siguiente texto dictado por voz para que sea un mensaje o prompt "
        "profesional, directo y técnico. Elimina muletillas, repeticiones y relleno "
        "conversacional. Corrige términos técnicos que el reconocimiento de voz haya "
        "transcrito mal cuando sea evidente por el contexto. No agregues contenido nuevo. "
        "Responde ÚNICAMENTE con el texto reescrito, sin comillas ni explicaciones."
    ),
}

_openai_client = None
_openai_warned = False


def _get_openai_client():
    global _openai_client, _openai_warned
    if _openai_client is not None:
        return _openai_client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        if not _openai_warned:
            print("[whisperflow] OPENAI_API_KEY no configurada; los perfiles de tono se "
                  "ignorarán y se pegará el texto normal", flush=True)
            _openai_warned = True
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
        return _openai_client
    except Exception as e:
        print(f"[whisperflow] no se pudo iniciar cliente OpenAI: {e}", flush=True)
        return None


def rewrite_with_llm(text, profile):
    system_prompt = PROFILE_PROMPTS.get(profile)
    if not system_prompt:
        return text
    client = _get_openai_client()
    if client is None:
        return text
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": text}],
            temperature=0.4,
        )
        rewritten = (resp.choices[0].message.content or "").strip()
        return rewritten or text
    except Exception as e:
        print(f"[whisperflow] error al reescribir con LLM ({profile}): {e}", flush=True)
        return text
