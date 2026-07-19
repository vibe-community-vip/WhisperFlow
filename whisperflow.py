# -*- coding: utf-8 -*-
"""
whisperflow.py — Dictado por voz local, offline, sin suscripción (reemplazo de Wispr Flow).

Dos atajos:
  - Ctrl + Win           -> push-to-talk puro: habla mientras sostienes ambas teclas;
                            al soltar cualquiera de las dos, transcribe y pega.
  - Ctrl + Win + Espacio -> modo "manos libres": sigue grabando aunque sueltes las teclas
                            (no necesitas sostener nada para seguir hablando). Para detener
                            y transcribir, vuelve a presionar Ctrl+Win (ya no hace falta
                            tocar Espacio de nuevo) o repite Ctrl+Win+Espacio.
  Si ya estabas en push-to-talk (Ctrl+Win sostenidos) y agregas Espacio a mitad de la
  grabación, esta se convierte en manos libres sin perder el audio ya grabado.
  - Ctrl + Alt + Z       -> vuelve a pegar el último texto transcrito (por si no había
                            campo de texto con foco cuando se dictó), igual que Wispr Flow.

Perfiles de tono (opcional): mientras estás grabando (push-to-talk o manos libres),
toca una vez (sin soltar nada más) alguna de estas teclas para que, antes de pegar,
el texto pase por un LLM (OpenAI) que le cambia el tono. Se bloquean (no se escriben
en el campo de texto) solo mientras se está grabando; el resto del tiempo funcionan
como teclas normales:
  - ,  -> "Amigable": agrega calidez, algo de emojis y signos de exclamación
         (para hablarle a un miembro de tu comunidad).
  - .  -> "Profesional": quita muletillas, es directo y técnico
         (para armar un prompt para una IA).
  - -  -> "Normal": cancela el perfil elegido y vuelve a pegar tal cual, sin pasar
         por el LLM (por si te arrepentiste de "," o ".").
  Si no tocas ninguna, se pega igual que siempre (sin pasar por el LLM). El indicador
  flotante en pantalla muestra el perfil elegido (ej. "Grabando (modo amigable)").
  Requiere la variable de entorno OPENAI_API_KEY; si no está configurada, se pega
  el texto normal y se avisa por consola.

Motor: faster-whisper, modelo "small", español. Carga con GPU (CUDA) si está disponible,
con fallback automático a CPU si no hay GPU o faltan las DLLs de CUDA.

El texto transcrito se pega en el campo de texto que tenga el foco (vía portapapeles + Ctrl+V),
igual que hace Wispr Flow.
"""
import os, sys, time, threading, io, wave, winsound, math
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Sin esto, en pantallas con escalado de Windows (125%/150%, típico en portátiles/4K),
# Tkinter no es consciente del DPI y Windows re-escala la ventana por su cuenta después
# de que ya calculamos su posición: el indicador flotante terminaba apareciendo movido
# de donde el código pedía (el bug que reportaste). Debe llamarse ANTES de crear cualquier
# ventana, así que va aquí arriba, antes del import de tkinter.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw

# Diccionario de precisión (3 niveles: initial_prompt + alias exactos + corrección
# difusa). Extraído a whisperflow/core/dictionary.py (módulo puro, multiplataforma).
from whisperflow.core.dictionary import (
    load_dictionary, build_initial_prompt, apply_aliases, apply_dictionary_corrections,
)

MODEL_SIZE = "small"       # ya cacheado localmente; rápido y preciso en español
LANGUAGE = "es"
SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# CUDA DLLs (idéntico a editor-videos-kevin/scripts/analyze.py) para que
# ctranslate2 encuentre cublas/cudnn instalados vía pip, sin depender de torch-CUDA.
def register_cuda_dlls():
    try:
        import nvidia
        for nbase in list(nvidia.__path__):
            for sub in ("cublas", "cudnn"):
                bindir = os.path.join(nbase, sub, "bin")
                if os.path.isdir(bindir):
                    os.add_dll_directory(bindir)
                    os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

register_cuda_dlls()
from faster_whisper import WhisperModel


def load_model():
    for dev, ct in [("cuda", "float16"), ("cuda", "int8_float16"), ("cuda", "int8"), ("cpu", "int8")]:
        try:
            m = WhisperModel(MODEL_SIZE, device=dev, compute_type=ct)
            print(f"[whisperflow] modelo '{MODEL_SIZE}' cargado en {dev}/{ct}", flush=True)
            return m
        except Exception as e:
            print(f"[whisperflow] no se pudo {dev}/{ct}: {str(e)[:120]}", flush=True)
    raise SystemExit("No se pudo cargar el modelo Whisper")


MODEL = load_model()

# ---------------------------------------------------------------------------
# Grabación de audio del micrófono por defecto

_current_mic_level = 0.0  # 0..1, actualizado en vivo por Recorder._callback


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._frames = []
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                           callback=self._callback)
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._frames.append(indata.copy())
        # Nivel de volumen en vivo, para las barritas animadas del indicador flotante.
        # No hace falta lock: es solo un float de lectura/escritura para algo cosmético,
        # y una lectura ligeramente "vieja" en la UI es inofensiva.
        global _current_mic_level
        rms = float(np.sqrt(np.mean(np.square(indata)))) if len(indata) else 0.0
        _current_mic_level = min(1.0, rms * 9.0)

    def stop(self):
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if not self._frames:
                return np.zeros((0,), dtype="float32")
            audio = np.concatenate(self._frames, axis=0).flatten()
            self._frames = []
            return audio


recorder = Recorder()

# (El diccionario de precisión — load_dictionary / build_initial_prompt /
#  apply_aliases / apply_dictionary_corrections — vive ahora en
#  whisperflow/core/dictionary.py, importado arriba. Comportamiento idéntico.)


# ---------------------------------------------------------------------------
# Perfiles de tono: segunda pasada opcional por un LLM (OpenAI) que reescribe el
# texto ya transcrito/corregido, antes de pegarlo. Se activan tocando B o N
# durante la grabación (ver _on_event). Si OPENAI_API_KEY no está configurada,
# se degrada de forma transparente: se pega el texto tal cual, sin reescritura.

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


# ---------------------------------------------------------------------------
# Señales sonoras (para saber qué está pasando sin necesidad de ventana/consola)

BEEP_VOLUME = 0.04  # 0.0 (silencio) - 1.0 (volumen máximo).
BEEP_SAMPLE_RATE = 44100  # tasa propia del beep, independiente de la del micrófono

def _make_beep_wav(freq, dur_ms, volume=BEEP_VOLUME, samplerate=BEEP_SAMPLE_RATE):
    n = int(samplerate * dur_ms / 1000)
    t = np.linspace(0, dur_ms / 1000, n, endpoint=False)
    tone = np.sin(2 * np.pi * freq * t)
    # fade in/out corto para evitar "click" audible al inicio/fin
    fade = min(n // 8, int(samplerate * 0.005)) or 1
    envelope = np.ones_like(tone)
    envelope[:fade] = np.linspace(0, 1, fade)
    envelope[-fade:] = np.linspace(1, 0, fade)
    samples = (tone * envelope * volume * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()

def _beep(freq, dur_ms):
    # winsound.PlaySound (WAV en memoria vía WinMM) en vez de sounddevice: sounddevice
    # comparte el mismo stream/dispositivo PortAudio que la grabación del micrófono
    # (sd.InputStream), y tocar un beep con sd.play() mientras se graba competía por
    # ese stream de forma intermitente (a veces sonaba, a veces no). WinMM es una ruta
    # de audio totalmente aparte, así que no interfiere con la grabación en curso.
    def _play():
        try:
            data = _make_beep_wav(freq, dur_ms)
            # Síncrono (sin SND_ASYNC) a propósito: combinar SND_MEMORY con SND_ASYNC deja
            # a Windows reproduciendo un buffer que Python puede recolectar (garbage-collect)
            # antes de que termine de sonar, cortando/silenciando el beep de forma aleatoria.
            # Como esto ya corre en su propio hilo, bloquear aquí no afecta al resto de la app.
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()

def beep_recording_start():
    _beep(880, 90)

def beep_hands_free_on():
    _beep(880, 70)
    threading.Timer(0.09, lambda: _beep(1200, 70)).start()

def beep_pasted():
    _beep(1400, 100)

def beep_no_speech():
    _beep(300, 180)

def beep_profile_friendly():
    _beep(1000, 60)

def beep_profile_professional():
    _beep(500, 60)

def beep_profile_reset():
    _beep(700, 60)


# ---------------------------------------------------------------------------
# Indicador visual flotante (igual que el de Wispr Flow): una píldora redondeada
# abajo al centro de la pantalla, con un mini-ecualizador que reacciona en vivo
# al volumen del micrófono mientras grabas. Aparece mientras grabas/transcribe y
# desaparece el resto del tiempo. Corre en su propio hilo con su propio Tk, y se
# le manda comandos por una cola desde el hilo del teclado.
#
# Se le quita el foco explícitamente (WS_EX_NOACTIVATE) para que mostrarla
# NUNCA le robe el foco al campo de texto donde estás dictando.

import queue as _queue

_overlay_queue = _queue.Queue()

_OVERLAY_STATE_COLOR = {
    "recording":  "#8ecae6",  # celeste suave (antes rojo, muy invasivo)
    "hands_free": "#b3a4e8",  # lavanda suave
    "processing": "#e8c98d",  # ámbar suave
}
_OVERLAY_TEXT_COLOR = "#d8d8dd"  # texto neutro; solo el punto/borde/barritas llevan el color de estado
_OVERLAY_STATE_TEXT = {
    "recording":  "Grabando",
    "hands_free": "Manos libres",
    "processing": "Procesando",
}
_OVERLAY_PROFILE_TEXT = {
    "friendly": "amigable",
    "professional": "profesional",
}

# Geometría de la píldora y de las barritas del ecualizador (a la derecha del texto).
# Mucho más chica que la primera versión (ocupaba como un quinto del ancho de pantalla).
_PILL_W, _PILL_H, _PILL_RADIUS = 240, 36, 15
_DOT_RADIUS = 3.5
_BAR_COUNT = 4
_BAR_W, _BAR_GAP = 3, 3
_BAR_MIN_H, _BAR_MAX_H = 3, 15
_BARS_AREA_W = _BAR_COUNT * _BAR_W + (_BAR_COUNT - 1) * _BAR_GAP
_PAD_LEFT, _PAD_RIGHT = 14, 12


def _rounded_rect_points(x1, y1, x2, y2, r):
    # 12 puntos de control que, con smooth=True, Tkinter interpola como una curva
    # continua: el resultado se ve como un rectángulo con esquinas redondeadas.
    return [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _overlay_thread_main():
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-toolwindow", True)
    except Exception:
        pass
    # OJO: nada de -alpha aquí. Windows renderiza el texto con ClearType (sub-pixel:
    # cada pixel se separa en franjas R/G/B para verse más nítido), y eso asume que sabe
    # exactamente qué color de fondo sólido hay detrás. -alpha vuelve la ventana translúcida
    # de verdad (mezcla cada pixel con lo que haya detrás en el escritorio), lo que rompe ese
    # supuesto y el texto sale con flecos de color (el "amarillo/naranja" que se veía en
    # "Grabando" no era el color que pedimos, era ese artefacto). -transparentcolor (abajo)
    # no tiene este problema porque sus pixeles son o 100% opacos o 100% invisibles, nunca
    # una mezcla parcial.

    W, H = _PILL_W, _PILL_H
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - 110}")

    # bg=magenta + transparentcolor: el canvas "de fondo" se vuelve invisible y solo se
    # ve la píldora redondeada que dibujamos encima, en vez de un rectángulo cuadrado.
    root.config(bg="#ff00ff")
    try:
        root.attributes("-transparentcolor", "#ff00ff")
    except Exception:
        pass

    canvas = tk.Canvas(root, width=W, height=H, bg="#ff00ff", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    pill = canvas.create_polygon(
        _rounded_rect_points(1, 1, W - 1, H - 1, _PILL_RADIUS),
        smooth=True, fill="#232328", outline="#8ecae6", width=1.5)

    dot_cx = _PAD_LEFT + _DOT_RADIUS
    dot = canvas.create_oval(dot_cx - _DOT_RADIUS, H / 2 - _DOT_RADIUS,
                              dot_cx + _DOT_RADIUS, H / 2 + _DOT_RADIUS,
                              fill="#8ecae6", outline="")

    text_x = dot_cx + _DOT_RADIUS + 7
    label = canvas.create_text(text_x, H // 2, text="", fill=_OVERLAY_TEXT_COLOR, anchor="w",
                                font=("Segoe UI Semibold", 9))

    bars_x0 = W - _PAD_RIGHT - _BARS_AREA_W
    bar_items = []
    for i in range(_BAR_COUNT):
        cx = bars_x0 + i * (_BAR_W + _BAR_GAP) + _BAR_W / 2
        item = canvas.create_rectangle(cx - _BAR_W / 2, H / 2 - _BAR_MIN_H / 2,
                                        cx + _BAR_W / 2, H / 2 + _BAR_MIN_H / 2,
                                        fill="#8ecae6", outline="")
        bar_items.append(item)

    root.update_idletasks()
    try:
        import win32gui, win32con
        hwnd = root.winfo_id()
        exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                exstyle | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
    except Exception as e:
        print(f"[whisperflow] overlay sin WS_EX_NOACTIVATE ({e}); puede robar foco", flush=True)

    root.withdraw()
    visible = False
    current_state = "recording"
    current_color = _OVERLAY_STATE_COLOR["recording"]
    bar_heights = [float(_BAR_MIN_H)] * _BAR_COUNT
    tick = 0

    def redraw_bars():
        nonlocal tick
        tick += 1
        if current_state in ("recording", "hands_free"):
            target_level = _current_mic_level
        elif current_state == "processing":
            target_level = 0.35 + 0.25 * math.sin(tick * 0.25)  # pulso tranquilo, sin mic en vivo
        else:
            target_level = 0.0

        for i, item in enumerate(bar_items):
            wobble = 0.75 + 0.25 * math.sin(tick * 0.35 + i * 0.7)  # da vidilla a cada barra
            target_h = _BAR_MIN_H + (_BAR_MAX_H - _BAR_MIN_H) * min(1.0, target_level * wobble)
            bar_heights[i] += (target_h - bar_heights[i]) * 0.35  # suaviza para que no se vea tembloroso
            half_h = bar_heights[i] / 2
            cx = bars_x0 + i * (_BAR_W + _BAR_GAP) + _BAR_W / 2
            canvas.coords(item, cx - _BAR_W / 2, H / 2 - half_h, cx + _BAR_W / 2, H / 2 + half_h)
            canvas.itemconfig(item, fill=current_color)

    def poll():
        nonlocal visible, current_state, current_color
        try:
            while True:
                cmd, payload = _overlay_queue.get_nowait()
                if cmd == "show":
                    state, profile = payload
                    current_state = state
                    current_color = _OVERLAY_STATE_COLOR.get(state, _OVERLAY_STATE_COLOR["recording"])
                    text = _OVERLAY_STATE_TEXT.get(state, _OVERLAY_STATE_TEXT["recording"])
                    if profile:
                        text += f" ({_OVERLAY_PROFILE_TEXT.get(profile, profile)})"
                    canvas.itemconfig(label, text=text)
                    canvas.itemconfig(dot, fill=current_color)
                    canvas.itemconfig(pill, outline=current_color)
                    if not visible:
                        root.deiconify()
                        visible = True
                elif cmd == "hide" and visible:
                    root.withdraw()
                    visible = False
                    for i in range(_BAR_COUNT):
                        bar_heights[i] = float(_BAR_MIN_H)
        except _queue.Empty:
            pass
        if visible:
            redraw_bars()
        root.after(40, poll)

    root.after(40, poll)
    root.mainloop()


def overlay_show(state, profile=None):
    _overlay_queue.put(("show", (state, profile)))


def overlay_hide():
    _overlay_queue.put(("hide", None))


threading.Thread(target=_overlay_thread_main, daemon=True).start()


# ---------------------------------------------------------------------------
# Transcripción + pegado en el campo con foco

_last_text_lock = threading.Lock()
_last_transcribed_text = None  # último texto transcrito, para poder recuperarlo con Ctrl+Alt+Z


def _clipboard_paste(text):
    # Soltamos Alt/Z por si este pegado fue disparado por un atajo que todavía sigue
    # físicamente presionado (ej. Ctrl+Alt+Z se detecta al bajar la Z, antes de que se
    # suelten los dedos). Si Alt sigue abajo cuando mandamos "ctrl+v", el campo de
    # destino recibe Ctrl+Alt+V en vez de Ctrl+V y no pega nada.
    try:
        keyboard.release("alt")
        keyboard.release("z")
    except Exception:
        pass

    prev_clipboard = None
    try:
        prev_clipboard = pyperclip.paste()
    except Exception:
        pass

    pyperclip.copy(text + " ")
    keyboard.send("ctrl+v")
    beep_pasted()

    if prev_clipboard is not None:
        def restore():
            time.sleep(0.6)
            try:
                pyperclip.copy(prev_clipboard)
            except Exception:
                pass
        threading.Thread(target=restore, daemon=True).start()


def transcribe_and_paste(audio, profile=None):
    global _last_transcribed_text
    try:
        duration = len(audio) / SAMPLE_RATE
        if duration < 0.25:
            print("[whisperflow] grabación demasiado corta, se ignora", flush=True)
            beep_no_speech()
            return
        terms, aliases = load_dictionary()
        initial_prompt = build_initial_prompt(terms)
        segments, _ = MODEL.transcribe(audio, language=LANGUAGE, beam_size=5,
                                        vad_filter=True, condition_on_previous_text=True,
                                        initial_prompt=initial_prompt)
        text = "".join(s.text for s in segments).strip()
        if not text:
            print("[whisperflow] no se detectó voz", flush=True)
            beep_no_speech()
            return
        text = apply_aliases(text, aliases)
        text = apply_dictionary_corrections(text, terms)

        if profile:
            print(f"[whisperflow] reescribiendo con perfil '{profile}'...", flush=True)
            text = rewrite_with_llm(text, profile)

        with _last_text_lock:
            _last_transcribed_text = text
        _clipboard_paste(text)
        print(f"[whisperflow] pegado: {text}", flush=True)
    finally:
        overlay_hide()


def recover_last_text():
    """Ctrl+Alt+Z: vuelve a pegar el último texto transcrito (igual que Wispr Flow),
    útil cuando se dictó sin tener un campo de texto con foco donde cayera el pegado."""
    with _last_text_lock:
        text = _last_transcribed_text
    if not text:
        beep_no_speech()
        print("[whisperflow] no hay texto previo que recuperar", flush=True)
        return
    _clipboard_paste(text)
    print(f"[whisperflow] recuperado: {text}", flush=True)


# ---------------------------------------------------------------------------
# Detección de los dos atajos: Ctrl+Win (push-to-talk) y Ctrl+Win+Espacio (manos libres)
#
# Ctrl+Win+Espacio siempre pasa primero por el estado "Ctrl+Win abajo" (la gente
# presiona los modificadores antes que Espacio), así que arrancamos a grabar en
# cuanto Ctrl+Win están ambos abajo (sin esperar nada -> cero audio perdido) y lo
# tratamos como push-to-talk provisional. Si Espacio se une mientras tanto, esa
# misma grabación se "asciende" a manos libres sin cortar ni reiniciar el audio.

_pressed = set()          # ctrl / windows actualmente abajo
_space_held = False       # evita reaccionar a la auto-repetición de Windows mientras Espacio sigue abajo
_recording_active = False
_hands_free = False
_state_lock = threading.Lock()

# Perfiles de tono (ver sección del LLM más arriba): se eligen tocando "," o "."
# mientras hay una grabación en curso (push-to-talk o manos libres); "-" cancela el
# perfil elegido y vuelve al modo normal (sin pasar por el LLM). Se eligieron estas
# teclas (en vez de letras) porque casi nunca hace falta teclearlas mientras se dicta.
PROFILE_KEYS = {",": "friendly", ".": "professional", "-": None}
_profile_key_held = {",": False, ".": False, "-": False}  # evita reaccionar a la auto-repetición mientras se mantiene abajo
_selected_profile = None  # perfil elegido para la grabación en curso (None = sin reescritura)


def _normalize(name):
    name = (name or "").lower()
    if "ctrl" in name:
        return "ctrl"
    if "windows" in name or name == "cmd":
        return "windows"
    if name == "space":
        return "space"
    return name


def _start_transcription(audio, profile=None):
    print("[whisperflow] transcribiendo...", flush=True)
    threading.Thread(target=transcribe_and_paste, args=(audio, profile), daemon=True).start()


DEBUG = os.environ.get("WHISPERFLOW_DEBUG") == "1"


def _on_event(event):
    global _recording_active, _hands_free, _space_held, _selected_profile
    key = _normalize(event.name)
    if DEBUG:
        print(f"[debug] raw_name={event.name!r} normalized={key!r} type={event.event_type} pressed={_pressed}",
              flush=True)
    if key not in ("ctrl", "windows", "space"):
        return

    with _state_lock:
        if key in ("ctrl", "windows"):
            if event.event_type == "down":
                _pressed.add(key)
                if {"ctrl", "windows"} <= _pressed:
                    if not _recording_active:
                        recorder.start()
                        _recording_active = True
                        _selected_profile = None
                        beep_recording_start()
                        overlay_show("recording")
                        print("[whisperflow] grabando (push-to-talk)...", flush=True)
                    elif _hands_free:
                        # En manos libres ya se habían soltado Ctrl/Win; volver a
                        # presionar ambas detiene la grabación y transcribe, sin
                        # necesidad de tocar Espacio de nuevo.
                        audio = recorder.stop()
                        _recording_active = False
                        _hands_free = False
                        profile, _selected_profile = _selected_profile, None
                        overlay_show("processing", profile)
                        _start_transcription(audio, profile)
            else:  # up
                _pressed.discard(key)
                if _recording_active and not _hands_free and not ({"ctrl", "windows"} <= _pressed):
                    # Se soltó Ctrl o Win antes de que se sumara Espacio -> push-to-talk termina aquí.
                    audio = recorder.stop()
                    _recording_active = False
                    profile, _selected_profile = _selected_profile, None
                    overlay_show("processing", profile)
                    _start_transcription(audio, profile)
            return

        # key == "space"
        if event.event_type == "down":
            if _space_held:
                return  # auto-repetición de Windows mientras se mantiene Espacio abajo: ignorar
            _space_held = True
            if not {"ctrl", "windows"} <= _pressed:
                return  # Espacio solo no activa nada
            if not _recording_active:
                recorder.start()
                _recording_active = True
                _selected_profile = None

            if _hands_free:
                # Segundo Ctrl+Win+Espacio: detener manos libres y transcribir.
                audio = recorder.stop()
                _recording_active = False
                _hands_free = False
                profile, _selected_profile = _selected_profile, None
                overlay_show("processing", profile)
                _start_transcription(audio, profile)
            else:
                # Primer Ctrl+Win+Espacio: asciende la grabación (nueva o ya en curso
                # como push-to-talk) a manos libres; seguirá aunque sueltes las teclas.
                _hands_free = True
                beep_hands_free_on()
                overlay_show("hands_free", _selected_profile)
                print("[whisperflow] modo manos libres activado (Ctrl+Win+Espacio de nuevo para detener)",
                      flush=True)
        else:  # up
            _space_held = False


def _make_profile_key_handler(key_name):
    # hook_key(..., suppress=True): a diferencia de keyboard.hook() (que solo observa),
    # esta variante puede BLOQUEAR la tecla para que no le llegue al campo de texto con
    # foco. Devolver True dentro del callback = dejar pasar la tecla normal (para no
    # romper el tipeo normal cuando no se está grabando); devolver False = bloquearla
    # (mientras se está grabando, para que ","/"."/"-" no se escriban en el campo de destino).
    def handler(event):
        global _selected_profile
        with _state_lock:
            if not _recording_active:
                return True  # no se está grabando: dejar que la tecla se escriba normal
            if event.event_type == "down":
                if _profile_key_held[key_name]:
                    return False  # auto-repetición de Windows mientras se mantiene abajo
                _profile_key_held[key_name] = True
                _selected_profile = PROFILE_KEYS[key_name]  # "-" pone esto en None (modo normal)
                if _selected_profile == "friendly":
                    beep_profile_friendly()
                elif _selected_profile == "professional":
                    beep_profile_professional()
                else:
                    beep_profile_reset()
                overlay_show("hands_free" if _hands_free else "recording", _selected_profile)
                label = _selected_profile or "normal (sin post-procesamiento)"
                print(f"[whisperflow] perfil de tono elegido: {label}", flush=True)
            else:  # up
                _profile_key_held[key_name] = False
            return False  # bloqueada: nunca se escribe en el campo de texto mientras se graba
    return handler


keyboard.hook(_on_event)
keyboard.add_hotkey("ctrl+alt+z", recover_last_text)
keyboard.hook_key(",", _make_profile_key_handler(","), suppress=True)
keyboard.hook_key(".", _make_profile_key_handler("."), suppress=True)
keyboard.hook_key("-", _make_profile_key_handler("-"), suppress=True)

# ---------------------------------------------------------------------------
# Icono en la bandeja del sistema

def make_icon_image():
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((14, 8, 50, 40), fill="white")
    d.rectangle((28, 40, 36, 52), fill="white")
    d.rectangle((18, 52, 46, 58), fill="white")
    return img


def on_quit(icon, item):
    icon.stop()
    os._exit(0)


def run_tray():
    icon = pystray.Icon("whisperflow", make_icon_image(), "WhisperFlow local (Ctrl+Win+Espacio)",
                         menu=pystray.Menu(pystray.MenuItem("Salir", on_quit)))
    icon.run()


if __name__ == "__main__":
    print("[whisperflow] listo. Ctrl+Win = push-to-talk. Ctrl+Win+Espacio = manos libres.", flush=True)
    run_tray()
