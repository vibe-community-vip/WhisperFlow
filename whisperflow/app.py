# -*- coding: utf-8 -*-
"""Orquestador de WhisperFlow: cablea backends + servicios y corre la bandeja.

La máquina de estados (cuándo grabar/transcribir/cambiar de perfil) vive aquí. Es
fiel al monolito original: la lógica de ``_on_event`` / ``_make_profile_key_handler``
se movió casi verbatim, pero opera sobre atributos de instancia y servicios
inyectados en vez de sobre globales de módulo. Sin cambio de comportamiento.
"""
import os
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from whisperflow.core import asr
from whisperflow.core.recorder import Recorder, SAMPLE_RATE
from whisperflow.core.dictionary import (
    load_dictionary, build_initial_prompt, apply_aliases, apply_dictionary_corrections,
)
from whisperflow.core import rewriter
from whisperflow.core import tray
from whisperflow.backends._selector import select_backends

# Teclas de perfil del monolito: "," amigable, "." profesional, "-" normal (None).
# Se eligieron estas teclas (no letras) porque casi nunca hace falta teclearlas
# mientras se dicta. "-" cancela el perfil elegido (vuelve a pegar tal cual).
PROFILE_KEYS = {",": "friendly", ".": "professional", "-": None}


class Application:
    def __init__(self, backends):
        self.beep = backends["beep"]()
        self.overlay = backends["overlay"]()
        self.hotkey = backends["hotkey"]()
        # El pegado necesita inyectar teclas (ctrl+v / cmd+v) vía el backend de hotkeys,
        # y tocar el beep de "pegado".
        self.paste = backends["paste"](self.hotkey, self.beep)
        self.recorder = Recorder()

        # Estado de la máquina de grabación (antes, globales de módulo).
        self._pressed = set()          # ctrl / windows actualmente abajo
        self._space_held = False       # evita reaccionar a la auto-repetición de Windows
        self._recording_active = False
        self._hands_free = False
        self._state_lock = threading.Lock()
        self._profile_key_held = {",": False, ".": False, "-": False}
        self._selected_profile = None  # perfil elegido para la grabación en curso (None = sin reescritura)

        # Último texto transcrito, para recuperarlo con Ctrl+Alt+Z.
        self._last_text_lock = threading.Lock()
        self._last_transcribed_text = None

        self.debug = os.environ.get("WHISPERFLOW_DEBUG") == "1"

        # Arranca el overlay en su propio hilo con su propio mainloop.
        self.overlay.start()

    # --- registro de hotkeys (mismo orden que el original: hook global, hotkey, suppressibles) ---
    def setup_hotkeys(self):
        self.hotkey.start(self.on_event)
        self.hotkey.register_hotkey("ctrl+alt+z", self.recover_last_text)
        for key in (",", ".", "-"):
            self.hotkey.register_suppressible_key(key, self.make_profile_key_handler(key))

    @staticmethod
    def _normalize(name):
        name = (name or "").lower()
        if "ctrl" in name:
            return "ctrl"
        if "windows" in name or name == "cmd":
            return "windows"
        if name == "space":
            return "space"
        return name

    # --- máquina de estados (movida verbatim de _on_event del monolito) ---
    def on_event(self, event):
        key = self._normalize(event.name)
        if self.debug:
            print(f"[debug] raw_name={event.name!r} normalized={key!r} "
                  f"type={event.event_type} pressed={self._pressed}", flush=True)
        if key not in ("ctrl", "windows", "space"):
            return

        with self._state_lock:
            if key in ("ctrl", "windows"):
                if event.event_type == "down":
                    self._pressed.add(key)
                    if {"ctrl", "windows"} <= self._pressed:
                        if not self._recording_active:
                            self.recorder.start()
                            self._recording_active = True
                            self._selected_profile = None
                            self.beep.recording_start()
                            self.overlay.show("recording")
                            print("[whisperflow] grabando (push-to-talk)...", flush=True)
                        elif self._hands_free:
                            # En manos libres ya se habían soltado Ctrl/Win; volver a
                            # presionar ambas detiene y transcribe, sin tocar Espacio otra vez.
                            audio = self.recorder.stop()
                            self._recording_active = False
                            self._hands_free = False
                            profile, self._selected_profile = self._selected_profile, None
                            self.overlay.show("processing", profile)
                            self.start_transcription(audio, profile)
                else:  # up
                    self._pressed.discard(key)
                    if self._recording_active and not self._hands_free and not ({"ctrl", "windows"} <= self._pressed):
                        # Se soltó Ctrl o Win antes de que se sumara Espacio -> push-to-talk termina aquí.
                        audio = self.recorder.stop()
                        self._recording_active = False
                        profile, self._selected_profile = self._selected_profile, None
                        self.overlay.show("processing", profile)
                        self.start_transcription(audio, profile)
                return

            # key == "space"
            if event.event_type == "down":
                if self._space_held:
                    return  # auto-repetición de Windows mientras Espacio sigue abajo
                self._space_held = True
                if not {"ctrl", "windows"} <= self._pressed:
                    return  # Espacio solo no activa nada
                if not self._recording_active:
                    self.recorder.start()
                    self._recording_active = True
                    self._selected_profile = None

                if self._hands_free:
                    # Segundo Ctrl+Win+Espacio: detener manos libres y transcribir.
                    audio = self.recorder.stop()
                    self._recording_active = False
                    self._hands_free = False
                    profile, self._selected_profile = self._selected_profile, None
                    self.overlay.show("processing", profile)
                    self.start_transcription(audio, profile)
                else:
                    # Primer Ctrl+Win+Espacio: asciende la grabación a manos libres;
                    # seguirá aunque sueltes las teclas (sin cortar el audio ya capturado).
                    self._hands_free = True
                    self.beep.hands_free_on()
                    self.overlay.show("hands_free", self._selected_profile)
                    print("[whisperflow] modo manos libres activado "
                          "(Ctrl+Win+Espacio de nuevo para detener)", flush=True)
            else:  # up
                self._space_held = False

    def make_profile_key_handler(self, key_name):
        # suppress=True (Windows): el handler devuelve True = dejar pasar la tecla
        # (no se está grabando, para no romper el tipeo normal), False = bloquearla
        # (mientras se graba, para que ","/"."/"-" no se escriban en el campo destino).
        def handler(event):
            with self._state_lock:
                if not self._recording_active:
                    return True
                if event.event_type == "down":
                    if self._profile_key_held[key_name]:
                        return False  # auto-repetición mientras se mantiene abajo
                    self._profile_key_held[key_name] = True
                    self._selected_profile = PROFILE_KEYS[key_name]  # "-" => None (modo normal)
                    if self._selected_profile == "friendly":
                        self.beep.profile_friendly()
                    elif self._selected_profile == "professional":
                        self.beep.profile_professional()
                    else:
                        self.beep.profile_reset()
                    self.overlay.show("hands_free" if self._hands_free else "recording", self._selected_profile)
                    label = self._selected_profile or "normal (sin post-procesamiento)"
                    print(f"[whisperflow] perfil de tono elegido: {label}", flush=True)
                else:  # up
                    self._profile_key_held[key_name] = False
                return False  # bloqueada mientras se graba
        return handler

    def start_transcription(self, audio, profile=None):
        print("[whisperflow] transcribiendo...", flush=True)
        threading.Thread(target=self.transcribe_and_paste, args=(audio, profile), daemon=True).start()

    def transcribe_and_paste(self, audio, profile=None):
        try:
            duration = len(audio) / SAMPLE_RATE
            if duration < 0.25:
                print("[whisperflow] grabación demasiado corta, se ignora", flush=True)
                self.beep.no_speech()
                return
            terms, aliases = load_dictionary()  # recarga en caliente (intencional: hot reload)
            initial_prompt = build_initial_prompt(terms)
            text = asr.transcribe(audio, initial_prompt=initial_prompt)
            if not text:
                print("[whisperflow] no se detectó voz", flush=True)
                self.beep.no_speech()
                return
            text = apply_aliases(text, aliases)
            text = apply_dictionary_corrections(text, terms)

            if profile:
                print(f"[whisperflow] reescribiendo con perfil '{profile}'...", flush=True)
                text = rewriter.rewrite_with_llm(text, profile)

            with self._last_text_lock:
                self._last_transcribed_text = text
            self.paste.paste(text)
            print(f"[whisperflow] pegado: {text}", flush=True)
        finally:
            self.overlay.hide()

    def recover_last_text(self):
        """Ctrl+Alt+Z: vuelve a pegar el último texto transcrito (igual que Wispr Flow)."""
        with self._last_text_lock:
            text = self._last_transcribed_text
        if not text:
            self.beep.no_speech()
            print("[whisperflow] no hay texto previo que recuperar", flush=True)
            return
        self.paste.paste(text)
        print(f"[whisperflow] recuperado: {text}", flush=True)

    def on_quit(self, icon, item):
        # os._exit(0) es intencional (ver CLAUDE.md): hay hilos daemon (overlay, audio,
        # transcripción) y el mainloop de pystray; un apagado "limpio" colgaría la salida.
        try:
            icon.stop()
        except Exception:
            pass
        os._exit(0)

    def run(self):
        self.setup_hotkeys()
        print("[whisperflow] listo. Ctrl+Win = push-to-talk. Ctrl+Win+Espacio = manos libres.",
              flush=True)
        tray.run_tray("WhisperFlow local (Ctrl+Win+Espacio)", self.on_quit)


def main():
    backends = select_backends()
    backends["startup_init"]()   # DPI awareness ANTES de importar tkinter
    app = Application(backends)
    app.run()
