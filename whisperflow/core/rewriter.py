# -*- coding: utf-8 -*-
"""Reescritura de tono vía LLM (núcleo multiplataforma) — Fase 3: selector de backend.

Tres backends, todos con la misma interfaz ``rewrite(text, profile)``:
  - OllamaRewriter: LLM LOCAL (recomendado, offline). Reutiliza el cliente OpenAI
    contra el endpoint compatible ``http://localhost:11434/v1`` (api_key indiferente).
  - OpenAIRewriter: OpenAI cloud (requiere ``OPENAI_API_KEY``).
  - NoopRewriter: no reescribe (devuelve el texto tal cual).

``select_rewriter()`` elige según ``WHISPERFLOW_LLM_BACKEND`` (``auto|ollama|openai|none``):
  - ``auto``: Ollama si responde (~200ms), si no OpenAI si hay key, si no Noop con
    aviso único. Es el default.
Cada ``rewrite`` tiene timeout (Ollama en frío puede tardar); si falla, se devuelve
el texto original y se avisa por consola (degradación elegante, igual que el monolito).
"""
import socket
import urllib.parse

from whisperflow.core import config

# Tiempo máx de una reescritura. Ollama puede tardar la primera vez (carga del modelo
# en RAM); si excede, devolvemos el texto original en lugar de colgar el pegado.
REWRITE_TIMEOUT = 30.0

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


class Rewriter:
    """Interfaz base. Cada subclase implementa ``rewrite``."""
    name = "none"

    def is_available(self) -> bool:
        return True

    def rewrite(self, text: str, profile: str) -> str:
        return text


class NoopRewriter(Rewriter):
    name = "none"


class OpenAIRewriter(Rewriter):
    name = "openai"

    def __init__(self):
        self._client = None
        self._warned = False

    def is_available(self):
        return bool(config.OPENAI_API_KEY)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not config.OPENAI_API_KEY:
            if not self._warned:
                print("[whisperflow] OPENAI_API_KEY no configurada; los perfiles de tono se "
                      "ignoran y se pegará el texto normal", flush=True)
                self._warned = True
            return None
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=config.OPENAI_API_KEY)
            return self._client
        except Exception as e:
            print(f"[whisperflow] no se pudo iniciar cliente OpenAI: {e}", flush=True)
            return None

    def rewrite(self, text, profile):
        system_prompt = PROFILE_PROMPTS.get(profile)
        if not system_prompt:
            return text
        client = self._get_client()
        if client is None:
            return text
        try:
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": text}],
                temperature=0.4,
                timeout=REWRITE_TIMEOUT,
            )
            rewritten = (resp.choices[0].message.content or "").strip()
            return rewritten or text
        except Exception as e:
            print(f"[whisperflow] error al reescribir con OpenAI ({profile}): {e}", flush=True)
            return text


class OllamaRewriter(Rewriter):
    name = "ollama"

    def __init__(self):
        self._client = None
        self._probe = None  # cache de la sonda de disponibilidad

    def is_available(self):
        """Sonda TCP corta (~200ms) al host:puerto del OLLAMA_BASE_URL."""
        if self._probe is not None:
            return self._probe
        try:
            u = urllib.parse.urlparse(config.OLLAMA_BASE_URL)
            host = u.hostname or "localhost"
            port = u.port or 11434
            with socket.create_connection((host, port), timeout=0.2):
                pass
            self._probe = True
        except Exception:
            self._probe = False
        return self._probe

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
            # api_key indiferente: Ollama no la valida; lo pide la firma del cliente.
            # base_url apunta al endpoint compatible /v1 de Ollama.
            self._client = OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
            return self._client
        except Exception as e:
            print(f"[whisperflow] no se pudo iniciar cliente Ollama: {e}", flush=True)
            return None

    def rewrite(self, text, profile):
        system_prompt = PROFILE_PROMPTS.get(profile)
        if not system_prompt:
            return text
        client = self._get_client()
        if client is None:
            return text
        try:
            resp = client.chat.completions.create(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": text}],
                temperature=0.4,
                timeout=REWRITE_TIMEOUT,
            )
            rewritten = (resp.choices[0].message.content or "").strip()
            return rewritten or text
        except Exception as e:
            print(f"[whisperflow] error al reescribir con Ollama ({profile}): {e}", flush=True)
            return text


_rewriter = None
_warned_auto = False


def select_rewriter() -> Rewriter:
    """Elige y cachea el rewriter según WHISPERFLOW_LLM_BACKEND. Idempotente."""
    global _rewriter, _warned_auto
    if _rewriter is not None:
        return _rewriter

    backend = config.LLM_BACKEND
    if backend == "none":
        _rewriter = NoopRewriter()
    elif backend == "openai":
        _rewriter = OpenAIRewriter()
    elif backend == "ollama":
        _rewriter = OllamaRewriter()
    else:  # "auto" (default)
        ollama = OllamaRewriter()
        if ollama.is_available():
            _rewriter = ollama
        else:
            openai = OpenAIRewriter()
            if openai.is_available():
                _rewriter = openai
            else:
                if not _warned_auto:
                    print("[whisperflow] sin backend de tono disponible: Ollama no responde y no "
                          "hay OPENAI_API_KEY. Los perfiles de tono se ignorarán.", flush=True)
                    _warned_auto = True
                _rewriter = NoopRewriter()

    print(f"[whisperflow] backend de tono activo: {_rewriter.name}", flush=True)
    return _rewriter


def get_rewriter() -> Rewriter:
    return select_rewriter()


def rewrite_with_llm(text: str, profile: str) -> str:
    """Compatibilidad: delega al rewriter seleccionado. app.py usa esta función."""
    return select_rewriter().rewrite(text, profile)
