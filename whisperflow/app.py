# -*- coding: utf-8 -*-
"""Orquestador de WhisperFlow: cablea backends + servicios y corre la bandeja.

La máquina de estados (cuándo grabar/transcribir/cambiar de perfil) vive aquí y es
**configurable** vía ``.env`` (``WHISPERFLOW_PTT_KEYS``/``HANDSFREE_KEY``/
``REPASTE_KEYS``/``WHISPERFLOW_PROFILE_KEYS``). Usa nombres canónicos de teclas:
``super`` (Win en Win/Linux, Cmd en Mac), ``ctrl``, ``alt``, ``shift``, ``space`` o un
carácter. Así una misma configuración sirve en todos los SO.
"""
import os
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from whisperflow.core import asr, config, history, recall, rewriter, tray, vad
from whisperflow.core.recorder import Recorder
from whisperflow.core.config import SAMPLE_RATE
from whisperflow.core.dictionary import (
    load_dictionary, build_initial_prompt, apply_aliases, apply_dictionary_corrections,
)
from whisperflow.backends._selector import select_backends


class Application:
    def __init__(self, backends):
        self.beep = backends["beep"]()
        self.overlay = backends["overlay"]()
        self.hotkey = backends["hotkey"]()
        self.paste = backends["paste"](self.hotkey, self.beep)
        self.recorder = Recorder()
        self.icon = None

        # Atajos configurables (canonical names).
        self.ptt_keys = set(config.PTT_KEYS)
        self.hf_key = config.HANDSFREE_KEY
        self.repaste_keys = list(config.REPASTE_KEYS)
        self.profile_keys = dict(config.PROFILE_KEYS)

        # Estado de la máquina de grabación.
        self._held = set()                 # teclas ptt actualmente abajo
        self._hf_key_held = False          # evita auto-repetición de la tecla manos-libres
        self._recording_active = False
        self._hands_free = False
        self._state_lock = threading.Lock()
        self._profile_key_held = {k: False for k in self.profile_keys}
        self._selected_profile = None

        self.debug = config.DEBUG

        if not self.ptt_keys:
            print("[whisperflow] AVISO: WHISPERFLOW_PTT_KEYS vacío -> no hay push-to-talk.",
                  flush=True)

        self.overlay.start()

    # --- registro de hotkeys ---
    def setup_hotkeys(self):
        self.hotkey.start(self.on_event)
        self.hotkey.register_hotkey(self.repaste_keys, self.recover_last_text)
        for key, profile in self.profile_keys.items():
            self.hotkey.register_suppressible_key(key, self.make_profile_key_handler(key, profile))

    @staticmethod
    def _normalize(name):
        """Nombre canónico de tecla: super/ctrl/alt/shift/space o el carácter tal cual."""
        n = (name or "").lower().strip()
        if "ctrl" in n or "control" in n:
            return "ctrl"
        if "windows" in n or "super" in n or "cmd" in n or "command" in n:
            return "super"
        if "alt" in n or "option" in n:
            return "alt"
        if n in ("shift", "shift_l", "shift_r", "left shift", "right shift"):
            return "shift"
        if n == "space":
            return "space"
        return n

    # --- máquina de estados (PTT + manos libres, config-driven) ---
    def on_event(self, event):
        key = self._normalize(event.name)
        if self.debug:
            print(f"[debug] raw={event.name!r} canonical={key!r} type={event.event_type} "
                  f"held={self._held}", flush=True)
        # Solo procesamos los modificadores del PTT y la tecla de manos libres.
        if key not in self.ptt_keys and key != self.hf_key:
            return

        with self._state_lock:
            if key in self.ptt_keys:
                if event.event_type == "down":
                    self._held.add(key)
                    if self.ptt_keys <= self._held:
                        if not self._recording_active:
                            if not asr.is_loaded():
                                self.overlay.show("loading"); self.beep.no_speech(); return
                            self.recorder.start()
                            self._recording_active = True
                            self._selected_profile = None
                            self.beep.recording_start()
                            self.overlay.show("recording")
                            print("[whisperflow] grabando (push-to-talk)...", flush=True)
                        elif self._hands_free:
                            # Re-presionar los modificadores detiene manos libres.
                            self._stop_and_transcribe()
                else:  # up
                    self._held.discard(key)
                    if self._recording_active and not self._hands_free \
                            and not (self.ptt_keys <= self._held):
                        self._stop_and_transcribe()
                return

            # key == hf_key
            if event.event_type == "down":
                if self._hf_key_held:
                    return  # auto-repetición
                self._hf_key_held = True
                if not (self.ptt_keys <= self._held):
                    return  # la tecla sola no hace nada
                if not self._recording_active:
                    if not asr.is_loaded():
                        self.overlay.show("loading"); self.beep.no_speech(); return
                    self.recorder.start()
                    self._recording_active = True
                    self._selected_profile = None
                if self._hands_free:
                    self._stop_and_transcribe()
                else:
                    self._hands_free = True
                    self.beep.hands_free_on()
                    self.overlay.show("hands_free", self._selected_profile)
                    print("[whisperflow] modo manos libres activado (atajo de nuevo para detener)",
                          flush=True)
            else:  # up
                self._hf_key_held = False

    def _stop_and_transcribe(self):
        # Llamado bajo self._state_lock.
        audio = self.recorder.stop()
        self._recording_active = False
        self._hands_free = False
        profile, self._selected_profile = self._selected_profile, None
        self.overlay.show("processing", profile)
        self.start_transcription(audio, profile)

    def make_profile_key_handler(self, key_name, profile):
        # Devuelve True = dejar pasar la tecla (no se graba), False = bloquearla.
        def handler(event):
            with self._state_lock:
                if not self._recording_active:
                    return True
                if event.event_type == "down":
                    if self._profile_key_held.get(key_name):
                        return False
                    self._profile_key_held[key_name] = True
                    self._selected_profile = profile
                    if profile == "friendly":
                        self.beep.profile_friendly()
                    elif profile == "professional":
                        self.beep.profile_professional()
                    else:
                        self.beep.profile_reset()
                    self.overlay.show("hands_free" if self._hands_free else "recording",
                                      self._selected_profile)
                    print(f"[whisperflow] perfil de tono: {profile or 'normal'}", flush=True)
                else:
                    self._profile_key_held[key_name] = False
                return False
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
            # VAD por energía: descarta capturas mudas ANTES de transcribir, para
            # evitar que Whisper alucine texto repetido sobre silencio.
            v = vad.evaluate(audio)
            if not v["speech"]:
                print(f"[whisperflow] no se detectó voz (VAD: peak={v['peak']:.4f} "
                      f"umbral={v['threshold']:.4f} tramas_activas={v['active']}/{v['n_frames']})",
                      flush=True)
                self.beep.no_speech()
                return
            terms, aliases = load_dictionary()
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

            recall.remember(text)
            history.append(text, profile)
            self.paste.paste(text)
            print(f"[whisperflow] pegado: {text}", flush=True)
        finally:
            self.overlay.hide()

    def recover_last_text(self):
        """Ctrl+Alt+Z: pega la grabación más reciente. Presionado varias veces
        seguidas SIN dictar nada nuevo en medio, retrocede a la anterior (hasta las
        últimas ``recall.MAX_RECALL``). Dictar algo nuevo reinicia el ciclo a la más
        reciente (ver ``transcribe_and_paste`` -> ``recall.remember``)."""
        text, idx, total = recall.recall_next()
        if not text:
            self.beep.no_speech()
            print("[whisperflow] no hay texto previo que recuperar", flush=True)
            return
        self.paste.paste(text)
        print(f"[whisperflow] recuperado ({idx}/{total}): {text}", flush=True)

    def _load_model_in_background(self):
        try:
            asr.ensure_loaded()
        except Exception as e:
            print(f"[whisperflow] FALLO la carga del modelo: {e}. "
                  "El dictado no estará disponible hasta resolverlo.", flush=True)
            return
        try:
            llm_name = rewriter.get_rewriter().name
        except Exception:
            llm_name = "?"
        if self.icon is not None:
            self.icon.title = f"WhisperFlow local (Ctrl+Win+Espacio) · LLM: {llm_name}"
            try:
                self.icon.update_menu()
            except Exception:
                pass
        print("[whisperflow] modelo listo.", flush=True)

    def on_quit(self, icon, item):
        # os._exit(0) es intencional (ver CLAUDE.md).
        try:
            icon.stop()
        except Exception:
            pass
        os._exit(0)

    def run(self):
        self.setup_hotkeys()
        self.icon = tray.build_icon("WhisperFlow local (cargando modelo…)", self.on_quit)
        if sys.platform == "darwin":
            # macOS: el overlay ya creó Tk en el hilo principal; pystray va detached y el
            # hilo principal queda en el mainloop de Tk (si pystray inicializa NSApplication
            # antes que Tk, este crashea).
            try:
                self.icon.run_detached()
            except Exception as e:
                print(f"[whisperflow] no se pudo iniciar la bandeja en Mac: {e}", flush=True)
        threading.Thread(target=self._load_model_in_background, daemon=True).start()
        print(f"[whisperflow] listo. PTT={'+'.join(sorted(self.ptt_keys))} "
              f"manos-libres=+{self.hf_key} re-pegar={'+'.join(self.repaste_keys)} "
              f"(motor ASR: {config.ASR_ENGINE})", flush=True)
        if sys.platform == "darwin":
            self.overlay.run_mainloop()
        else:
            tray.run_icon(self.icon)


def main():
    backends = select_backends()
    backends["startup_init"]()
    app = Application(backends)
    app.run()
